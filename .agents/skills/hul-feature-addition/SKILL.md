---
name: hul-feature-addition
description: Architecture standards and design patterns for adding new features, upstream reports, API endpoints, or database models to HUL Distributor ERP (myerpv3). Use when implementing new business logic, adding new IKEA/GST/NIC reports, building new REST endpoints, or extending internal accounting ledgers.
---

# Skill: HUL ERP Feature Addition & Integration Patterns

> Usage Type: **New Feature Addition, API Expansion & Scraper Extension**  
> Shared Domain Brain: [docs/APPS_GUIDE.md](file:///home/ubuntu/myerpv3/docs/APPS_GUIDE.md) and [docs/CLASSES_GUIDE.md](file:///home/ubuntu/myerpv3/docs/CLASSES_GUIDE.md)

---

## 1. Architectural Guardrails for New Code

1. **Domain App Placement**: Consult the [12-App Responsibility Matrix](file:///home/ubuntu/myerpv3/docs/APPS_GUIDE.md#1-app-by-app-navigation-directory). Do not create new Django apps; place models and views in the appropriate existing app.
2. **EC2 Memory Budget**: EC2 RAM is strictly limited. Always paginate querysets, chunk file processing, and **never use Selenium/Playwright on request threads**.
3. **Multitenancy by Design**: All business entities must inherit from [`core.models.CompanyModel`](file:///home/ubuntu/myerpv3/core/models.py#L52) or link to `Organization`.
4. **Scraper Hygiene**: Never hand-roll `requests` calls. Always extend [`custom.Session`](file:///home/ubuntu/myerpv3/custom/Session.py#L24) or add methods to [`Ikea`](file:///home/ubuntu/myerpv3/custom/classes.py#L439), [`Gst`](file:///home/ubuntu/myerpv3/custom/classes.py#L930), or [`Einvoice`](file:///home/ubuntu/myerpv3/custom/classes.py#L1245).

---

## 2. Standard Pattern A: Adding a New IKEA / Portal Report

Follow these 5 steps whenever integrating a new report from IKEA Leveredge:

### Step 1: Capture and Save Working cURL
- In browser DevTools Network tab, locate the working report generation request.
- Right-click $\rightarrow$ **Copy as cURL (bash)**.
- Save to `custom/curl/<portal>/<report_name>.txt` (e.g. `custom/curl/ikea/new_report.txt`). Strip out hardcoded cookies.

### Step 2: Recompile `all_curls.py`
- Run:
  ```python
  from custom.curl import interpret_all_curls
  interpret_all_curls()
  ```

### Step 3: Add Fetcher Method in `custom/classes.py`
- Add to [`IkeaReports`](file:///home/ubuntu/myerpv3/custom/classes.py#L198):
  ```python
  @ikea_screen("Report Screen Name")  # Crucial: Prevents "Screen Already Exists"
  def new_report(self, fromd: datetime.date, tod: datetime.date) -> pd.DataFrame:
      return self.fetch_report_dataframe(
          "ikea/new_report",
          r'(":val1":").{10}(",":val2":").{10}',
          (fromd.strftime("%d/%m/%Y"), tod.strftime("%d/%m/%Y"))
      )
  ```

### Step 4: Define Report Model in `report/models.py`
- Choose base class:
  - Date range reports: inherit [`DateReportModel`](file:///home/ubuntu/myerpv3/report/models.py#L211).
  - Snapshot / master reports: inherit [`EmptyReportModel`](file:///home/ubuntu/myerpv3/report/models.py#L257).
  ```python
  class NewReport(DateReportModel):
      inum = models.CharField(max_length=30)
      amt = models.FloatField()
      # Define fields matching cleaned DataFrame columns

      class Report(DateReportModel.Report):
          fetcher = IkeaReports.new_report
          column_map = {"Bill No": "inum", "Amount": "amt"}
          dropna_columns = ["inum"]
          
          def custom_preprocessing(self, df: pd.DataFrame) -> pd.DataFrame:
              # Custom business logic / cleaning
              return df
  ```

### Step 5: (Optional) Wire into `erp/erp_import.py`
- If this report should feed internal double-entry accounting tables, add a transformation class to `erp/erp_import.py` and register it in `GstFilingImport.imports`.

---

## 3. Standard Pattern B: Adding a New REST API Endpoint

1. **View Definition in `<app>/views.py`**:
   ```python
   from rest_framework.decorators import api_view, permission_classes
   from rest_framework.permissions import IsAuthenticated
   from rest_framework.response import Response
   from gst.api import check_login
   from custom.classes import Ikea

   @api_view(["POST"])
   @permission_classes([IsAuthenticated])
   @check_login(Ikea)  # If external IKEA session is required
   def new_feature_view(request):
       company_id = request.data.get("company")
       # Business logic scoped to request.user.organization or company
       return Response({"status": "success"})
   ```
2. **URL Registration**:
   - Register route in `<app>/urls.py`.
   - Ensure the app's URLs are included in [`myerpv2/urls.py`](file:///home/ubuntu/myerpv3/myerpv2/urls.py).
3. **Response Protocol**:
   - Return HTTP `200` with JSON payload on success.
   - Return HTTP `501 {"key": "<portal>"}` if external portal session is expired.
   - Return HTTP `400` with descriptive `error` message on bad input.

---

## 4. Standard Pattern C: Adding Models with Composite Primary Keys

The project uses Django 5.1+ composite keys and multi-column foreign relationships:

```python
from django.db import models
from core.models import CompanyModel

class NewEntity(CompanyModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    pk = models.CompositePrimaryKey("company", "code")

    # Multi-column relationship to Party
    party = models.ForeignObject(
        "erp.Party",
        on_delete=models.DO_NOTHING,
        null=True,
        from_fields=("company", "code"),
        to_fields=("company", "code"),
    )
```

**Rule for Bulk Inserts**:
Always use `bulk_create` with conflict handling:
```python
NewEntity.objects.bulk_create(new_records, ignore_conflicts=True)
```
