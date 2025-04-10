"""
Outlook邮件处理模块
"""

import imaplib
import email
import requests
from datetime import datetime
import threading
import socket
import time

from .common import (
    decode_mime_words,
    strip_html,
    safe_decode,
    remove_extra_blank_lines,
    normalize_check_time,
    format_date_for_imap_search,
)
from .logger import logger

class OutlookMailHandler:
    """Outlook邮箱处理类"""
    
    @staticmethod
    def get_new_access_token(refresh_token, client_id="9e5f94bc-e8a4-4e73-b8be-63364c29d753"):
        """刷新获取新的access_token"""
        tenant_id = 'common'
        refresh_token_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': client_id,
        }

        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        try:
            response = requests.post(token_url, data=refresh_token_data)
            if response.status_code == 200:
                new_access_token = response.json().get('access_token')
                logger.info(f"成功获取新的访问令牌")
                return new_access_token
            else:
                logger.error(f"刷新令牌失败: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"刷新令牌过程中发生异常: {str(e)}")
            return None

    @staticmethod
    def generate_auth_string(user, token):
        """生成 OAuth2 授权字符串"""
        return f"user={user}\1auth=Bearer {token}\1\1"

    @staticmethod
    def fetch_emails(email_address, access_token, folder="INBOX", callback=None, last_check_time=None):
        """
        通过IMAP协议获取Outlook/Hotmail邮箱中的邮件
        
        Args:
            email_address: 邮箱地址
            access_token: OAuth2访问令牌
            folder: 邮件文件夹，默认为收件箱
            callback: 进度回调函数
            last_check_time: 上次检查时间，如果提供，只获取该时间之后的邮件
            
        Returns:
            list: 邮件记录列表
        """
        mail_records = []
        
        # 确保回调函数存在
        if callback is None:
            callback = lambda progress, folder: None
            
        # 标准化处理last_check_time
        last_check_time = normalize_check_time(last_check_time)
            
        # 日志记录
        if last_check_time:
            logger.info(f"获取Outlook邮箱{email_address}中{folder}文件夹自{last_check_time.isoformat()}以来的新邮件")
        else:
            logger.info(f"获取Outlook邮箱{email_address}中{folder}文件夹的所有邮件")
        
        # 尝试连接次数
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                logger.info(f"尝试连接Outlook邮箱 (尝试 {retry+1}/{max_retries})")
                callback(10, folder)
                
                # 创建IMAP连接
                mail = imaplib.IMAP4_SSL('outlook.office365.com')
                
                # 使用OAuth2登录
                auth_string = OutlookMailHandler.generate_auth_string(email_address, access_token)
                mail.authenticate('XOAUTH2', lambda x: auth_string)
                
                # 选择文件夹
                mail.select(folder)
                callback(20, folder)
                
                # 定义搜索条件
                if last_check_time:
                    # 将上次检查时间转换为IMAP日期格式 (DD-MMM-YYYY)
                    search_date = format_date_for_imap_search(last_check_time)
                    search_cmd = f'(SINCE "{search_date}")'
                    logger.info(f"搜索{search_date}之后的邮件")
                    status, data = mail.search(None, search_cmd)
                else:
                    # 获取最近的100封邮件
                    status, data = mail.search(None, 'ALL')
                
                if status != 'OK':
                    logger.error(f"搜索邮件失败: {status}")
                    continue
                
                # 获取所有邮件ID
                mail_ids = data[0].split()
                
                # 只处理最近的100封邮件
                mail_ids = mail_ids[-100:] if len(mail_ids) > 100 else mail_ids
                
                total_mails = len(mail_ids)
                logger.info(f"找到{total_mails}封邮件")
                
                # 处理每封邮件
                for i, mail_id in enumerate(mail_ids):
                    # 更新进度
                    progress = int(20 + (i / total_mails) * 70) if total_mails > 0 else 90
                    callback(progress, folder)
                    
                    try:
                        # 获取邮件
                        status, mail_data = mail.fetch(mail_id, '(RFC822)')
                        
                        if status != 'OK':
                            logger.error(f"获取邮件ID {mail_id} 失败: {status}")
                            continue
                        
                        # 解析邮件
                        msg = email.message_from_bytes(mail_data[0][1])
                        
                        # 获取邮件基本信息
                        subject = decode_mime_words(msg.get('Subject', ''))
                        sender = decode_mime_words(msg.get('From', ''))
                        received_time = email.utils.parsedate_to_datetime(msg.get('Date', ''))
                        
                        # 创建唯一标识，用于去重
                        mail_key = f"{subject}|{sender}|{received_time.isoformat() if received_time else 'unknown'}"
                        
                        # 检查此邮件是否已处理（通过内存中的集合进行快速检查）
                        if mail_key in [record.get('mail_key') for record in mail_records]:
                            logger.info(f"跳过重复邮件: {subject}")
                            continue
                        
                        # 获取邮件内容
                        content = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if content_type == 'text/plain' or content_type == 'text/html':
                                    try:
                                        part_content = part.get_payload(decode=True).decode()
                                        content += part_content
                                    except:
                                        pass
                        else:
                            content = msg.get_payload(decode=True).decode()
                        
                        # 添加到结果列表
                        mail_records.append({
                            'subject': subject,
                            'sender': sender,
                            'received_time': received_time,
                            'content': content,
                            'mail_key': mail_key  # 添加唯一标识，用于后续去重
                        })
                        
                    except Exception as e:
                        logger.error(f"处理邮件ID {mail_id} 时出错: {str(e)}")
                
                # 成功获取邮件，跳出重试循环
                callback(90, folder)
                break
                
            except imaplib.IMAP4.error as e:
                logger.error(f"IMAP错误: {str(e)}")
                time.sleep(1)  # 等待一秒再重试
                
            except Exception as e:
                logger.error(f"获取邮件异常: {str(e)}")
                time.sleep(1)  # 等待一秒再重试
                
            finally:
                # 确保关闭连接
                try:
                    mail.logout()
                except:
                    pass
        
        return mail_records

    @staticmethod
    def check_mail(email_info, db, progress_callback=None):
        """检查Outlook/Hotmail邮箱中的邮件并存储到数据库"""
        email_id = email_info['id']
        email_address = email_info['email']
        refresh_token = email_info['refresh_token']
        client_id = email_info['client_id']
        
        logger.info(f"开始检查Outlook邮箱: ID={email_id}, 邮箱={email_address}")
        
        # 确保回调函数存在
        if progress_callback is None:
            progress_callback = lambda progress, message: None
        
        # 报告初始进度
        progress_callback(0, "正在获取访问令牌...")
        
        try:
            # 获取新的访问令牌
            access_token = OutlookMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                error_msg = f"邮箱{email_address}(ID={email_id})获取访问令牌失败"
                logger.error(error_msg)
                progress_callback(0, error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
            
            # 更新令牌到数据库
            db.update_email_token(email_id, access_token)
            
            # 报告进度
            progress_callback(10, "开始获取邮件...")
            
            # 获取邮件
            def folder_progress_callback(progress, folder):
                msg = f"正在处理{folder}文件夹，进度{progress}%"
                # 将各文件夹的进度映射到总进度10-90%
                total_progress = 10 + int(progress * 0.8)
                progress_callback(total_progress, msg)
            
            try:
                mail_records = OutlookMailHandler.fetch_emails(
                    email_address, 
                    access_token, 
                    "INBOX", 
                    folder_progress_callback
                )
                
                # 报告进度
                count = len(mail_records)
                progress_callback(90, f"获取到{count}封邮件，正在保存...")
                
                # 将邮件记录保存到数据库
                saved_count = 0
                for record in mail_records:
                    try:
                        success = db.add_mail_record(
                            email_id, 
                            record['subject'], 
                            record['sender'], 
                            record['received_time'], 
                            record['content']
                        )
                        if success:
                            saved_count += 1
                    except Exception as e:
                        logger.error(f"保存邮件记录失败: {str(e)}")
                
                # 更新最后检查时间
                try:
                    db.update_check_time(email_id)
                except Exception as e:
                    logger.error(f"更新检查时间失败: {str(e)}")
                
                # 报告完成
                success_msg = f"完成，共处理{count}封邮件，新增{saved_count}封"
                progress_callback(100, success_msg)
                
                logger.info(f"邮箱{email_address}(ID={email_id})检查完成，获取到{count}封邮件，新增{saved_count}封")
                return {
                    'success': True,
                    'message': success_msg,
                    'total': count,
                    'saved': saved_count
                }
                
            except Exception as e:
                error_msg = f"检查邮件失败: {str(e)}"
                logger.error(f"邮箱{email_address}(ID={email_id}){error_msg}")
                progress_callback(0, error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
                
        except Exception as e:
            error_msg = f"处理邮箱过程中出错: {str(e)}"
            logger.error(f"邮箱{email_address}(ID={email_id}){error_msg}")
            progress_callback(0, error_msg)
            return {
                'success': False,
                'message': error_msg
            } 