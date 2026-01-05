from report.models import OutstandingReport
from rest_framework import serializers
from bank.models import ChequeDeposit,BankStatement,BankCollection,Bank
from drf_writable_nested import WritableNestedModelSerializer
from core.models import Company

class BankCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankCollection
        fields = ["bill","amt","party","company","balance"]

class ChequeSerializer(WritableNestedModelSerializer):
    collection = BankCollectionSerializer(many=True)
    party_name = serializers.SlugField(source="party.name", read_only=True)
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    bank_entry = serializers.SlugField(source="bank_entry.id", read_only=True)
    class Meta:
        model = ChequeDeposit
        fields = ["id","company",
                        "cheque_date","cheque_no","party_id","party_name","amt","bank","deposit_date",
                        "collection","party","bank_entry"]

class BankSerializer(WritableNestedModelSerializer):
    collection = BankCollectionSerializer(many=True) #Only Neft Collection
    bank = serializers.SlugField(source="bank.name", read_only=True)
    class Meta:
        model = BankStatement
        fields = ["date","company","ref","desc","amt","bank","status","pushed","type","id",
                       "cheque_entry","cheque_status","collection"]

class BankNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ["id", "name"]