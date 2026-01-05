from bank.views import predict_party
from bank.models import BankStatement

id = 53746
obj = BankStatement.objects.get(id= id)
print(predict_party(obj.desc,obj.bank_id))
