import smtplib
import ssl
from email.message import EmailMessage

# 1. Configuration
SMTP_SERVER = "email-smtp.ap-south-1.amazonaws.com"
PORT = 465  
USERNAME_SMTP = "AKIA3IXCLYEJW47ZSJSE"
PASSWORD_SMTP = "BCUluDrJ5x4SUubu7Hk21x98M9HfvuSae03UtDvCIxb9"

msg = EmailMessage()
msg["Subject"] = "ERP Login Notification"
msg["From"] = "noreply@devaki.shop"
msg["To"] = "venkateshks2304@gmail.com"
msg.set_content("This is a test email from your Mumbai-based SES endpoint.")
with open("a.xlsx", "rb") as f:
    file_data = f.read()
    msg.add_attachment(
        file_data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Monthly_Report.xlsx"
    )

context = ssl.create_default_context()
with smtplib.SMTP_SSL(SMTP_SERVER, PORT, context=context) as server:
    server.login(USERNAME_SMTP, PASSWORD_SMTP)
    server.send_message(msg)



print("Email sent via Port 465!")