from core.models import User
from io import BytesIO
import pandas as pd
from custom.classes import Einvoice, Gst, IkeaDownloader
from core.models import Company, UserSession

User.objects.filter(username='murugan').delete()
User.objects.filter(username='devaki').delete()
# UserSession.objects.filter(user='devaki_hul').delete()

user = User.objects.create_user(username='devaki', password='1')
company = Company.objects.create(name="devaki_hul",user = user,gst_types = ["sales","salesreturn","claimservice"])


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

# UserSession(
#     user="murugan",
#     key="einvoice",
#     username="unify@2018",
#     password="Rs411474&#58",
#     config={
#         "seller_json": {
#             "SellerDtls": {
#                 #This needs to be changed
#                 # "Gstin": "33AAPFD1365C1ZR",
#                 # "LglNm": "DEVAKI ENTERPRISES",
#                 # "Addr1": "F/4 , INDUSTRISAL ESTATE , ARIYAMANGALAM",
#                 # "Loc": "TRICHY",
#                 # "Pin": 620010,
#                 # "Stcd": "33",
#             }
#         }
#     },
# ).save()

exit(0)
