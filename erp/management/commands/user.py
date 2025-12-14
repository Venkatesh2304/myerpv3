from core.models import User
from io import BytesIO
import pandas as pd
from custom.classes import Einvoice, Gst
from core.models import Company, UserSession

# User.objects.filter(username='devaki').delete()
# UserSession.objects.filter(user='devaki_hul').delete()

user = User.objects.create_user(username='devaki', password='1')
for company_name in ["devaki_hul","lakme_rural","lakme_urban"] :
    company = Company.objects.create(name=company_name,user = user,gst_types = ["sales","salesreturn","claimservice"])
    company.save()

#Ikea Session
UserSession(
    user="devaki_hul",
    key="ikea",
    username="IIT",
    password="Ven@1234",
    config={
        "dbName": "41A392",
        "home": "https://leveredge18.hulcd.com",
        "bill_prefix" : "A",
        "auto_delivery_process" : True
    },
).save(force_insert=False)

UserSession(
    user="lakme_urban",
    key="ikea",
    username="IIT",
    password="aBC@2025",
    config={
        "dbName": "41B864",
        "home": "https://leveredge11.hulcd.com",
        "bill_prefix" : "CA",
        "auto_delivery_process" : True
    },
).save(force_insert=False)

UserSession(
    user="lakme_rural",
    key="ikea",
    username="IIT",
    password="Abc@2025",
    config={
        "dbName": "41B862",
        "home": "https://leveredge57.hulcd.com",
        "bill_prefix" : "CB",
        "auto_delivery_process" : True
    },
).save(force_insert=False)



# i = IkeaDownloader("devaki_rural")
# print(i.get("/rsunify/app/billing/getUserId").text)


# #Gst Session
# UserSession(
#     user="murugan",
#     key="gst",
#     username="angalamman.64_8",
#     password="Murugan@$456",
#     config={
#         "gstin" : "33ACMPD8352Q1Z3"
#     }
# ).save()
# # g = Gst("devaki")
# # for cookie in g.cookies :
# #     print(cookie.name,cookie.value)
# # while not g.is_logged_in() :
# #     with open("captcha.png","wb+") as f :
# #         f.write(g.captcha())
# #     captcha_input = input("Enter Captcha : ")
# #     status = g.login(captcha_input)
# #     print("Login status : ",status)
# # print("Gst Logged in successfully")

UserSession(
    user="murugan",
    key="einvoice",
    username="DEVAKI9999",
    password="Mosl@123",
    config={
        "seller_json": {
            "SellerDtls": {
                #This needs to be changed
                "Gstin": "33AAPFD1365C1ZR",
                "LglNm": "DEVAKI ENTERPRISES",
                "Addr1": "F/4 , INDUSTRISAL ESTATE , ARIYAMANGALAM",
                "Loc": "TRICHY",
                "Pin": 620010,
                "Stcd": "33",
            }
        }
    },
).save()

exit(0)
