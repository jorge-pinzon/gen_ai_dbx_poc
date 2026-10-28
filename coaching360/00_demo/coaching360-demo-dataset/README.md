# Coaching360 demo dataset

> [!WARNING]
> **Synthetic data, provisional schema.** Every person, branch, account, and number in this
> package is generated. None of it comes from production or QA. The tables follow the
> **current** Coaching360 sources (Coaching360 app database, BranchKPI, Reports.KPIDashboard,
> BranchDirectory, RiskRanking staging, CRM ACE procedures, EDA Ref, and PolicyViolations).
> **These shapes will change when Coaching360 connects to the data warehouse (DW).** Expect
> renamed and consolidated tables, different keys (for example DW surrogate keys instead of
> BranchNumber, TellerID, Year/Month), and KPI definitions that move into DW views. Treat
> column names as illustrative. Use them for prototyping and scoping, and do not hard-code
> them into anything long-lived.


Generated 2026-10-20 with `scripts/generate_coaching360_demo_dataset.py` (as-of date 2026-10-20, random seed 360).
Re-running with the same seed and as-of date reproduces the same data.

## What's inside

| Path | Contents |
|---|---|
| `csv/` | One CSV per table, grouped by source system (UTF-8, header row, empty field = NULL) |
| `coaching360_demo.sqlite` | All tables in one SQLite file. `_tables` and `_columns` hold the metadata |
| `DATA_DICTIONARY.md` | Every table and column, with grain, source system, and notes |

| Folder | Source system today | Rows |
|---|---|---|
| `01_org_hierarchy` | EDA reference database (Ref schema) | 602 |
| `02_branchkpi_sources` | BranchKPI database (HQ) | 127,084 |
| `03_risk_ranking` | Staging database (RiskRanking data) | 1,627 |
| `04_crm_ace_payout` | CRM database (stored procedure result sets) | 5,782 |
| `05_policy_violations` | PolicyViolations database (app schema) | 931 |
| `06_coaching360_app_reference` | Coaching360 application database (dbo) | 730 |
| `07_coaching360_app_workflow` | Coaching360 application database (dbo) | 157,575 |
| `08_coaching360_app_dpr` | Coaching360 application database (dbo) (loaded by external python_etl job) | 25,879 |

## The synthetic organization

- 1 division, 3 field regions, 9 districts, and 62 field branches (branch numbers 8001+), plus a headquarters branch (`1`) with Branch Enablement (Branch Assist) staff and app administrators.
- 397 people, including former employees who left during the window. AR turnover runs at roughly 25% a year, so the turnover KPIs and inactive-employee cases have real data.
- KPI history runs monthly from 2025-01 to the month before the as-of date. Workflow activity (coaching, Success Plans, accountability meetings, branch visits, tasks, notifications) runs from 2026-01-05 to 2026-10-20.
- Each employee has a hidden skill level and each branch a hidden quality factor. Together they drive the KPIs, so the same people stay strong or weak across LPE, delinquency, first lien, calls, DPR, and ACE payout tiers.
- The workflow responds to the KPIs. KPI-triggered coaching targets each employee's weakest prior-month metric and quotes the actual value. Low performers get coached more often, and recognition goes to people above goal. Success Plan `MonthlyKpiGoals` JSON is built from the same KPI rows.

## Keys that join the sources together

| Key | Where it appears |
|---|---|
| `UserDWID` (500001+) | EDA `T_Ref_User.UserDWID`. The app stores it as `EmployeeId`, `ManagerEmployeeId`, `AuthorEmployeeId`, `AssignedToEmployeeId`, `RecipientEmployeeId`, and similar columns |
| `TellerID` (9100000xx) | BranchKPI `EmployeePerformance`, `UserTeller`, `CallData`, `EmployeeGoals`, ACE `TELLER_ID`, DPR `SourceTellerId`, app `Employees.EmployeeNumber` |
| `AssociateId` / `EmployeeNumber` | EDA `T_Ref_User.EmployeeNumber`, ACE `AssociateID`, PolicyViolations `EmployeeId` |
| `BranchNumber` (8001+) | BranchKPI `Branch`, EDA `T_Ref_Branch.BranchNumber`, PolicyViolations `BranchNumber`, the first 4 digits of `AcctNum` |
| `BranchDWID` (3001+) | EDA `T_Ref_Branch.BranchDWID`. The app stores it as `OrganizationalUnitId` |
| `DistrictNumber` (901-909) | BranchKPI district tables, EDA `T_Ref_District.DistrictNumber`, ACE AVP `districtnumber` |
| `Employees.EmployeeId` | App internal id, used only by the DPR tables. Map it through `Employees.ExternalEmployeeId` = UserDWID |

## Deliberate omissions

- Binary attachment content is NULL. File names, types, and sizes are included.
- `DataProtectionKeys` is empty because it holds security material. `OrganizationalUnits`, `KpiScoreSnapshots`, `Tags`, `EntityTags`, and `RolePageAccessOverrides` are also empty, matching production, where the app does not populate them.
- DPR staging and rejection rows cover only the two most recent ETL batches. The batch history and the published metrics are complete.
- Email delivery is shown as disabled (`Queued`), which matches non-production configuration.
- Names come from generic name lists, and every email uses the reserved `demo.example.com` domain. Any resemblance to real employees is coincidental.

## Regenerate

```
python scripts/generate_coaching360_demo_dataset.py --as-of 2026-10-20 --seed 360
```
