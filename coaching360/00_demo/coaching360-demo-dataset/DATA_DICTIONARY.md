# Coaching360 demo dataset: data dictionary

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


## 01_org_hierarchy

### EDA.Ref.T_Ref_CompanyDivision

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_CompanyDivision.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_CompanyDivision`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per company division
- **Rows:** 1

Top of the org hierarchy (SVP level). Coaching360 reads it for Policy Violations and via the Security API BranchHierarchy endpoint.

| Column | Source type | Notes |
|---|---|---|
| CompanyDivisionDWID | int | Warehouse surrogate key |
| DivisionNumber | nvarchar(20) |  |
| DivisionName | nvarchar(200) |  |
| SVPUsername | nvarchar(256) |  |
| SVPName | nvarchar(200) |  |
| SVPEmail | nvarchar(320) |  |

### EDA.Ref.T_Ref_Region

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_Region.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_Region`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per region
- **Rows:** 4

Regions (RVP level). RegionNumber is a string in the source.

| Column | Source type | Notes |
|---|---|---|
| RegionDWID | int |  |
| CompanyDivisionDWID | int | FK -> T_Ref_CompanyDivision |
| RegionNumber | nvarchar(20) |  |
| RegionName | nvarchar(200) |  |
| VPUsername | nvarchar(256) |  |
| VPName | nvarchar(200) |  |
| VPEmail | nvarchar(320) |  |

### EDA.Ref.T_Ref_District

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_District.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_District`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per district
- **Rows:** 10

Districts (DM / AVP level). DistrictNumber is text in EDA and an int in BranchKPI.

| Column | Source type | Notes |
|---|---|---|
| DistrictDWID | int |  |
| RegionDWID | int | FK -> T_Ref_Region |
| DistrictNumber | nvarchar(20) |  |
| DistrictName | nvarchar(200) |  |
| DMUsername | nvarchar(256) |  |
| DMName | nvarchar(200) |  |
| DMEmail | nvarchar(320) |  |

### EDA.Ref.T_Ref_Branch

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_Branch.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_Branch`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per branch (current snapshot)
- **Rows:** 63

Branches with current BM and optional relief manager. Branch 1 is headquarters (central staff, Branch Assist). Branch numbers 8001+ are synthetic.

| Column | Source type | Notes |
|---|---|---|
| BranchDWID | int |  |
| DistrictDWID | int | FK -> T_Ref_District |
| BranchNumber | int | 4-digit business key used by KPI sources |
| BranchName | nvarchar(200) |  |
| BranchState | char(2) | Drives state goals, ROA floor and peer groups |
| BranchType | nvarchar(40) | FieldBranch / CentralBranch |
| BMUsername | nvarchar(256) |  |
| BMName | nvarchar(200) |  |
| BMEmail | nvarchar(320) |  |
| ReliefManagerUsername | nvarchar(256) |  |
| ReliefManager | nvarchar(200) |  |
| ReliefManagerEmail | nvarchar(320) |  |
| ReliefManagerStartDate | date |  |
| ReliefManagerEndDate | date |  |

### EDA.Ref.T_Ref_User

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_User.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_User`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per user (active and inactive)
- **Rows:** 397

Employee directory. TellerID is the join key into every KPI source; UserDWID is the key the Coaching360 app stores on workflow rows.

| Column | Source type | Notes |
|---|---|---|
| UserDWID | int | Warehouse user key; stored by Coaching360 as EmployeeId on workflow tables |
| UserName | nvarchar(256) | Bare AD login (domain stripped) |
| EmployeeNumber | nvarchar(64) | HR associate id (string); key for ACE payout |
| Name | nvarchar(200) |  |
| UserTitle | nvarchar(200) | Job title; drives role aliases and DPR eligibility |
| Department | nvarchar(200) |  |
| ManagerUserName | nvarchar(256) |  |
| UserEmail | nvarchar(320) |  |
| EmployeeActive | bit |  |
| BranchDWID | int | FK -> T_Ref_Branch |
| TellerID | nvarchar(64) | Loosely typed in source; TRY_CONVERT(bigint) on read |
| SeniorityDate | date |  |
| TerminationDate | date | Synthetic convenience column; not present in EDA today |

### EDA.Ref.T_Ref_UserGroups

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_UserGroups.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_UserGroups`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per user x AD group
- **Rows:** 17

AD security group membership. Only used today to identify Branch Assist / Branch Enablement staff.

| Column | Source type | Notes |
|---|---|---|
| UserName | nvarchar(256) |  |
| GroupName | nvarchar(256) |  |

### EDA.Ref.T_Ref_ApplicationRoles

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_ApplicationRoles.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_ApplicationRoles`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per Coaching360 application role
- **Rows:** 12

Assignable application roles. Employee User is computed (not assignable); BM/DM/VP/SVP get Branch/Central Operations from the hierarchy.

| Column | Source type | Notes |
|---|---|---|
| ApplicationId | int |  |
| RoleId | int |  |
| RoleName | nvarchar(120) |  |
| Description | nvarchar(400) |  |

### EDA.Ref.T_Ref_ApplicationUserRole

- **File:** `csv/01_org_hierarchy/EDA_Ref_T_Ref_ApplicationUserRole.csv` (SQLite table `org_hierarchy__EDA_Ref_T_Ref_ApplicationUserRole`)
- **Source system:** EDA reference database (Ref schema)
- **Grain:** One row per user x role grant
- **Rows:** 26

Explicit role grants (Security API GetUserRoles). Field BMs receive Branch Operations from the hierarchy alias and need no row.

| Column | Source type | Notes |
|---|---|---|
| ApplicationId | int |  |
| RoleId | int | FK -> T_Ref_ApplicationRoles |
| UserName | nvarchar(256) |  |
| IsActive | bit |  |

### BranchDirectory.Ref.T_Ref_Branch

- **File:** `csv/01_org_hierarchy/BranchDirectory_Ref_T_Ref_Branch.csv` (SQLite table `org_hierarchy__BranchDirectory_Ref_T_Ref_Branch`)
- **Source system:** BranchDirectory database (Ref schema)
- **Grain:** One row per field branch (current snapshot)
- **Rows:** 62

Directory headcount and Branch Manager Trainee (BMT) window. An active BMT reduces the employee denominator for LPE/DACC.

| Column | Source type | Notes |
|---|---|---|
| BranchNumber | varchar(10) | Text in source; TRY_CONVERT(int) on read |
| DistrictDWID | int |  |
| Employees | numeric |  |
| BMT | varchar(200) |  |
| BMTUsername | varchar(256) |  |
| BMTEmail | varchar(320) |  |
| BMTStartDate | date |  |
| BMTEndDate | date |  |

### BranchDirectory.Ref.T_Ref_District

- **File:** `csv/01_org_hierarchy/BranchDirectory_Ref_T_Ref_District.csv` (SQLite table `org_hierarchy__BranchDirectory_Ref_T_Ref_District`)
- **Source system:** BranchDirectory database (Ref schema)
- **Grain:** One row per district
- **Rows:** 10

Maps DistrictDWID to the district number.

| Column | Source type | Notes |
|---|---|---|
| DistrictDWID | int |  |
| DistrictNumber | varchar(10) |  |

## 02_branchkpi_sources

### BranchKPI.Monthly.EmployeePerformance

- **File:** `csv/02_branchkpi_sources/BranchKPI_Monthly_EmployeePerformance.csv` (SQLite table `branchkpi_sources__BranchKPI_Monthly_EmployeePerformance`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per TellerID x Branch x Year x Month
- **Rows:** 5,593

Employee monthly production and delinquency. Feeds the Individual Daily Production Scorecard, peer ranks, and IDP monthly KPI goals.

| Column | Source type | Notes |
|---|---|---|
| Branch | int |  |
| Year | int |  |
| Month | int |  |
| TellerID | bigint | Join key to UserTeller, CallData, EDA T_Ref_User |
| BranchState | char(2) | Peer-group partition |
| WorkingDays | int |  |
| StateTotalTellers | int |  |
| TotalLoans | int |  |
| LPE | decimal | Loans per employee-day; goal 1.0 |
| DACC_Loans | int | Goal 2 per month |
| DLQCurrentMonthPerc_Actual | decimal | Fraction |
| DLQCurrentMonthPerc_Goal | decimal | Fraction (state goal) |
| DLQ3060DayPerc_Actual | decimal | 30-89 day DLQ actual, fraction (column name says 30-60) |
| DLQ3089DayPerc_Goal | decimal | Fraction |
| Employee_Cash_Advance | money |  |
| Total_State_Cash_Advance | money |  |
| Average_State_Cash_Advance | money |  |
| MonthlyNewCashNetAdvance | money |  |
| FirstLienPercentage | decimal | Count-based % |
| FirstLienVolumePercentage | decimal | Volume-based % |
| FirstLienVolumeDollars | money |  |
| TotalVolumeDollars | money |  |

### BranchKPI.Monthly.BranchPerformance

- **File:** `csv/02_branchkpi_sources/BranchKPI_Monthly_BranchPerformance.csv` (SQLite table `branchkpi_sources__BranchKPI_Monthly_BranchPerformance`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per Branch x Year x Month
- **Rows:** 1,302

Branch / BM monthly scorecard inputs.

| Column | Source type | Notes |
|---|---|---|
| Branch | int |  |
| Year | int |  |
| Month | int |  |
| BranchState | char(2) |  |
| Employees | numeric | Monthly employee count (LPE/DACC denominator) |
| HeadCount | numeric | Approved headcount |
| Direct_Loans_MTD_LPE | decimal | Branch LPE |
| BM_LPE | decimal |  |
| TotalBMLoans | int |  |
| Branch_DACC_Loans | int |  |
| BM_DACC_Loans | int |  |
| DLQCurrentMonthPerc_Actual | decimal | Fraction; 2026+ scored on raw actual (lower is better) |
| DLQCurrentMonthPerc_Goal | decimal |  |
| DLQ3060DayPerc_Actual | decimal |  |
| DLQ3089DayPerc_Goal | decimal |  |
| ROA_Percentage | decimal | Branch ROA as % of company average |
| Branch_ROA_Percentage | decimal | Raw ROA %, compared to RoaStateFloor |
| All_ROA_Avg_Percentage | decimal |  |
| FirstLienPercentage | decimal |  |
| FirstLienVolumePercentage | decimal |  |
| FirstLienVolumeDollars | money |  |
| TotalVolumeDollars | money |  |
| NonAffiliateAppPerApprovedHeadcount | decimal |  |
| PBRenewal | decimal | % |
| ConversionCombo | decimal | % |
| DARPDealsBooked | int |  |
| CreditGrade45UnsecuredUtilizationRate | decimal | Fraction; displayed x100, goal 75% |

### BranchKPI.Monthly.DistrictPerformance

- **File:** `csv/02_branchkpi_sources/BranchKPI_Monthly_DistrictPerformance.csv` (SQLite table `branchkpi_sources__BranchKPI_Monthly_DistrictPerformance`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per DistrictNumber x Year x Month
- **Rows:** 189

District / AVP monthly scorecard inputs. Region and company rollups do not exist in the app today.

| Column | Source type | Notes |
|---|---|---|
| DistrictNumber | int |  |
| Year | int |  |
| Month | int |  |
| Branches | int |  |
| NoOfBranchs | int | DARP denominator (sic) |
| Employees | numeric |  |
| DistrictLPE | decimal |  |
| District_DACC_LPE | decimal |  |
| District_DACC_Loans | numeric |  |
| DLQCurrentMonthPerc_Goal | decimal |  |
| DLQ_CurrentMonth_PercentageTotal | decimal | Whole %; 2026+ only |
| DLQ_CurrentMonth_Percentage | decimal | Legacy goal/actual ratio % |
| DLQ_30_89_Percentage | decimal | Goal/actual ratio % |
| ROA_Percentage | decimal |  |
| FirstLienPercentage | decimal |  |
| FirstLienVolumePercentage | decimal |  |
| FirstLienVolumeDollars | money |  |
| TotalVolumeDollars | money |  |
| TurnoverScore | decimal | Legacy (pre-2026) turnover % |
| DARPDealsBooked | int |  |
| CreditGrade45UnsecuredUtilizationRate | decimal | 2026+ only |

### BranchKPI.Monthly.TurnoverGoal

- **File:** `csv/02_branchkpi_sources/BranchKPI_Monthly_TurnoverGoal.csv` (SQLite table `branchkpi_sources__BranchKPI_Monthly_TurnoverGoal`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per DistrictNumber x Year x Month
- **Rows:** 189

Monthly district turnover %. 2026+ district Turnover KPI = SUM of the trailing 12 months (lower is better).

| Column | Source type | Notes |
|---|---|---|
| DistrictNumber | int |  |
| Year | int |  |
| Month | int |  |
| TurnoverScore | decimal(18,6) |  |

### BranchKPI.Monthly.BranchTurnoverGoal

- **File:** `csv/02_branchkpi_sources/BranchKPI_Monthly_BranchTurnoverGoal.csv` (SQLite table `branchkpi_sources__BranchKPI_Monthly_BranchTurnoverGoal`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per BranchNumber x Report_Date
- **Rows:** 1,302

Branch YTD turnover. Still queried but no longer displayed (retired from the BM scorecard).

| Column | Source type | Notes |
|---|---|---|
| BranchNumber | int |  |
| Report_Date | date |  |
| YTDTurnoverScore | decimal |  |

### BranchKPI.dbo.RoaStateFloor

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_RoaStateFloor.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_RoaStateFloor`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per StateCode x ReviewYear
- **Rows:** 18

Minimum branch ROA % by state; below floor = Does Not Meet.

| Column | Source type | Notes |
|---|---|---|
| StateCode | char(2) |  |
| ReviewYear | int |  |
| RoaFloor | decimal |  |

### BranchKPI.dbo.UserTeller

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_UserTeller.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_UserTeller`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per TellerId
- **Rows:** 389

Bridges TellerId to login, associate id and name for KPI rows.

| Column | Source type | Notes |
|---|---|---|
| TellerId | bigint |  |
| UserName | varchar(256) |  |
| AssociateId | varchar(64) |  |
| FullName | varchar(200) |  |

### BranchKPI.dbo.ReviewCommentApproval

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_ReviewCommentApproval.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_ReviewCommentApproval`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per branch (or district) x ReportDate x ReviewType
- **Rows:** 6

Branch/district months excluded from rolling averages (shown as X).

| Column | Source type | Notes |
|---|---|---|
| Branch | int |  |
| District | int |  |
| ReportDate | date |  |
| ReviewType | varchar(40) |  |
| ExclusionComment | varchar(2000) |  |
| IsExcluded | bit |  |

### BranchKPI.dbo.PerformanceMeasurement

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_PerformanceMeasurement.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_PerformanceMeasurement`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per measure (MeasureId)
- **Rows:** 33

Legacy BranchKPI measure catalog (date-effective). App-owned KpiScoringRules override these when mapped.

| Column | Source type | Notes |
|---|---|---|
| Id | int |  |
| Title | varchar(200) |  |
| ReviewType | varchar(40) | Branch / District / Employee |
| StartDate | date |  |
| EndDate | date |  |

### BranchKPI.dbo.PerformanceGoal

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_PerformanceGoal.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_PerformanceGoal`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per goal version
- **Rows:** 33

Display goal text per measure.

| Column | Source type | Notes |
|---|---|---|
| Id | int |  |
| MeasurementId | int | FK -> PerformanceMeasurement.Id |
| Goal | varchar(100) |  |
| StartDate | date |  |
| EndDate | date |  |

### BranchKPI.dbo.PerformanceExpectation

- **File:** `csv/02_branchkpi_sources/BranchKPI_dbo_PerformanceExpectation.csv` (SQLite table `branchkpi_sources__BranchKPI_dbo_PerformanceExpectation`)
- **Source system:** BranchKPI database (HQ)
- **Grain:** One row per goal x band
- **Rows:** 132

Legacy expectation bands: label of the highest Level whose Limit <= value (lower-is-better measures invert).

| Column | Source type | Notes |
|---|---|---|
| GoalId | int | FK -> PerformanceGoal.Id |
| Label | varchar(120) |  |
| Limit | decimal |  |
| Level | int |  |

### Reports.KPIDashboard.CallData

- **File:** `csv/02_branchkpi_sources/Reports_KPIDashboard_CallData.csv` (SQLite table `branchkpi_sources__Reports_KPIDashboard_CallData`)
- **Source system:** Reports database (KPIDashboard schema)
- **Grain:** One row per TellerID x call_date (weekdays)
- **Rows:** 117,162

Daily outbound call activity; summed to month for the Outbound Calls KPI.

| Column | Source type | Notes |
|---|---|---|
| TellerID | bigint |  |
| call_date | date |  |
| OutboundCalls | int |  |
| OutboundContacts | int |  |
| TotalContacts | int |  |

### Reports.KPIDashboard.Goals

- **File:** `csv/02_branchkpi_sources/Reports_KPIDashboard_Goals.csv` (SQLite table `branchkpi_sources__Reports_KPIDashboard_Goals`)
- **Source system:** Reports database (KPIDashboard schema)
- **Grain:** One row per goal
- **Rows:** 2

Goal catalog for the KPI dashboard.

| Column | Source type | Notes |
|---|---|---|
| GoalID | int |  |
| GoalName | varchar(120) |  |

### Reports.KPIDashboard.EmployeeGoals

- **File:** `csv/02_branchkpi_sources/Reports_KPIDashboard_EmployeeGoals.csv` (SQLite table `branchkpi_sources__Reports_KPIDashboard_EmployeeGoals`)
- **Source system:** Reports database (KPIDashboard schema)
- **Grain:** One row per TellerID x GoalID
- **Rows:** 734

Monthly outbound call/contact targets (not period-filtered).

| Column | Source type | Notes |
|---|---|---|
| TellerID | bigint |  |
| GoalID | int | FK -> Goals.GoalID |
| TargetValue | decimal |  |

## 03_risk_ranking

### Staging.dbo.RiskRankingUnsecured

- **File:** `csv/03_risk_ranking/Staging_dbo_RiskRankingUnsecured.csv` (SQLite table `risk_ranking__Staging_dbo_RiskRankingUnsecured`)
- **Source system:** Staging database (RiskRanking data)
- **Grain:** One row per loan account (credit grade 4/5 unsecured)
- **Rows:** 1,627

Account-level unsecured utilization. Branch = LEFT(AcctNum, 4). The app now displays the precomputed BranchPerformance rate; this path is legacy.

| Column | Source type | Notes |
|---|---|---|
| AcctNum | varchar(20) | Synthetic; first 4 digits = branch number |
| UnsecuredDollars | decimal(38,6) |  |
| UnsecuredLimit | decimal(38,6) |  |

## 04_crm_ace_payout

### CRM.Ace.usp_GetBMEmployeeMonthlyPayoutEstimate

- **File:** `csv/04_crm_ace_payout/CRM_Ace_usp_GetBMEmployeeMonthlyPayoutEstimate.csv` (SQLite table `crm_ace_payout__CRM_Ace_usp_GetBMEmployeeMonthlyPayoutEstimate`)
- **Source system:** CRM database (stored procedure result sets)
- **Grain:** One row per AssociateID x month (procedure called per associate with @Month = month-end)
- **Rows:** 5,593

ACE incentive payout estimate. Tier = first positive of HR > Triple > Double > Single > Walk > Bunt. Materialized here as a table of procedure results.

| Column | Source type | Notes |
|---|---|---|
| AssociateID | varchar(64) | Procedure parameter @AssociateID |
| REPORT_DATE | date |  |
| Month | int |  |
| Month_Name | varchar(20) |  |
| Branch | int |  |
| HR | int |  |
| Triple | int |  |
| Double | int |  |
| Single | int |  |
| Walk | int |  |
| Bunt | int |  |
| BMlpe | int |  |
| WorkingDays | int |  |
| PayClass | varchar(20) | BM / Employee |
| BMPayout | decimal |  |
| TELLER_ID | bigint |  |
| EmpEstPayout | decimal |  |
| BMEstPayout | decimal |  |
| Column_1 | varchar(100) |  |
| Column_2 | varchar(100) |  |
| Column_3 | varchar(100) |  |

### CRM.Ace.usp_GetAVPMonthlyPayoutEstimate

- **File:** `csv/04_crm_ace_payout/CRM_Ace_usp_GetAVPMonthlyPayoutEstimate.csv` (SQLite table `crm_ace_payout__CRM_Ace_usp_GetAVPMonthlyPayoutEstimate`)
- **Source system:** CRM database (stored procedure result sets)
- **Grain:** One row per district x month (procedure called with @districtnumber, @Month)
- **Rows:** 189

District manager (AVP) ACE payout estimate.

| Column | Source type | Notes |
|---|---|---|
| districtnumber | varchar(10) | Procedure parameter |
| REPORT_DATE | date |  |
| Month | int |  |
| Month_Name | varchar(20) |  |
| EstPayout | decimal |  |

## 05_policy_violations

### PolicyViolations.app.Policies

- **File:** `csv/05_policy_violations/PolicyViolations_app_Policies.csv` (SQLite table `policy_violations__PolicyViolations_app_Policies`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per policy
- **Rows:** 6

Policy catalog.

| Column | Source type | Notes |
|---|---|---|
| PolicyId | int identity |  |
| PolicyName | nvarchar(200) |  |
| IsActive | bit |  |
| IsOptionalProductPolicy | bit |  |
| ModifiedDate | datetime |  |

### PolicyViolations.app.ViolationTypes

- **File:** `csv/05_policy_violations/PolicyViolations_app_ViolationTypes.csv` (SQLite table `policy_violations__PolicyViolations_app_ViolationTypes`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per violation type
- **Rows:** 12

Violation types with required-field flags.

| Column | Source type | Notes |
|---|---|---|
| ViolationTypeId | int |  |
| PolicyId | int | FK -> Policies |
| Code | nvarchar(80) |  |
| Name | nvarchar(200) |  |
| Description | nvarchar(1000) |  |
| IsActive | bit |  |
| RequiresManagerAcknowledgement | bit |  |
| RequiresAccountNumber | bit |  |
| RequiresApplicationNumber | bit |  |
| RequiresApplicationReceivedDate | bit |  |
| RequiresGloOfferAmount | bit |  |
| RequiresGloExpirationDate | bit |  |
| RequiresDefermentsIn12Months | bit |  |
| RequiresDefermentsLifetime | bit |  |
| RequiresOptionalProductsPurchased | bit |  |
| ModifiedDate | datetime |  |

### PolicyViolations.app.Accounts

- **File:** `csv/05_policy_violations/PolicyViolations_app_Accounts.csv` (SQLite table `policy_violations__PolicyViolations_app_Accounts`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per PV system user account
- **Rows:** 3

Users who enter violations (compliance/admin).

| Column | Source type | Notes |
|---|---|---|
| AccountId | int identity |  |
| EmployeeId | nvarchar(64) |  |
| DisplayName | nvarchar(200) |  |
| UserName | nvarchar(256) |  |
| EmailAddress | nvarchar(320) |  |

### PolicyViolations.app.Violations

- **File:** `csv/05_policy_violations/PolicyViolations_app_Violations.csv` (SQLite table `policy_violations__PolicyViolations_app_Violations`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per policy violation
- **Rows:** 190

Employee policy violations with management chain, escalation level (1-3) and manager acknowledgement. Coaching360 reads and writes these.

| Column | Source type | Notes |
|---|---|---|
| ViolationId | int identity |  |
| PayloadJson | nvarchar(max) |  |
| EmployeeId | nvarchar(64) | Associate id |
| EmployeeUserName | nvarchar(256) |  |
| EmployeeName | nvarchar(200) |  |
| EmployeeEmail | nvarchar(320) |  |
| BranchNumber | int |  |
| BranchName | nvarchar(200) |  |
| DirectManagerUserName | nvarchar(256) |  |
| DirectManagerName | nvarchar(200) |  |
| DirectManagerEmail | nvarchar(320) |  |
| ManagementChainJson | nvarchar(max) | Array of {Sequence, UserName, Name, Email, Title} |
| PolicyId | int |  |
| PolicyName | nvarchar(200) |  |
| ViolationTypeId | int |  |
| ViolationTypeName | nvarchar(200) |  |
| Description | nvarchar(2000) |  |
| Source | nvarchar(100) |  |
| ViolationDate | date |  |
| SourceCreatedDate | datetime |  |
| CreatedAt | datetime |  |
| UpdatedAt | datetime |  |
| AccountNumber | nvarchar(40) |  |
| ApplicationNumber | nvarchar(40) |  |
| ApplicationReceivedDate | date |  |
| GloOfferAmount | decimal |  |
| GloExpirationDate | date |  |
| DefermentsIn12Months | int |  |
| DefermentsLifetime | int |  |
| OptionalProductsPurchased | nvarchar(400) |  |
| CorrectiveActionNotes | nvarchar(2000) |  |
| TrainingAssigned | nvarchar(400) |  |
| CorrectiveActionDueDate | date |  |
| Status | nvarchar(60) | Submitted / Acknowledged / CorrectiveActionInProgress / CorrectiveActionCompleted / Migrated |
| EscalationLevel | int | 1-3 |
| RequiredAction | nvarchar(200) |  |
| ManagerAcknowledged | bit |  |
| ManagerAcknowledgedBy | nvarchar(256) |  |
| ManagerAcknowledgedAt | datetime |  |
| ManagerAcknowledgementNotes | nvarchar(2000) |  |
| EnteredByUserName | nvarchar(256) |  |
| UpdatedByUserName | nvarchar(256) |  |
| LegacySource | nvarchar(100) |  |
| LegacySourceId | bigint |  |
| AccountId | int | FK -> Accounts |
| EmploymentStatus | nvarchar(40) | Derived from the directory at read time; convenience column |

### PolicyViolations.app.NotificationHistory

- **File:** `csv/05_policy_violations/PolicyViolations_app_NotificationHistory.csv` (SQLite table `policy_violations__PolicyViolations_app_NotificationHistory`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per violation x notification type x send
- **Rows:** 203

Notification log for violations.

| Column | Source type | Notes |
|---|---|---|
| NotificationHistoryId | int identity |  |
| ViolationId | int |  |
| NotificationType | nvarchar(80) |  |
| SentDate | datetime |  |
| IsSuccess | bit |  |
| LegacySourceDateColumn | nvarchar(400) | Subject / status text |
| CreatedDate | datetime |  |

### PolicyViolations.app.AuditLog

- **File:** `csv/05_policy_violations/PolicyViolations_app_AuditLog.csv` (SQLite table `policy_violations__PolicyViolations_app_AuditLog`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per violation action
- **Rows:** 490

Audit log for violations.

| Column | Source type | Notes |
|---|---|---|
| AuditLogId | int identity |  |
| ViolationId | int |  |
| ActionType | nvarchar(80) |  |
| ActionBy | nvarchar(256) |  |
| ActionDate | datetime |  |
| Details | nvarchar(2000) |  |
| LegacySource | nvarchar(100) |  |
| LegacySourceId | bigint |  |
| CreatedDate | datetime |  |

### PolicyViolations.app.ViolationAttachment

- **File:** `csv/05_policy_violations/PolicyViolations_app_ViolationAttachment.csv` (SQLite table `policy_violations__PolicyViolations_app_ViolationAttachment`)
- **Source system:** PolicyViolations database (app schema)
- **Grain:** One row per attachment
- **Rows:** 27

Violation attachments; binary Content omitted (NULL).

| Column | Source type | Notes |
|---|---|---|
| ViolationAttachmentId | bigint identity |  |
| ViolationId | int |  |
| FileName | nvarchar(260) |  |
| ContentType | nvarchar(160) |  |
| FileSizeBytes | bigint |  |
| Content | varbinary(max) | Omitted |
| UploadedBy | nvarchar(256) |  |
| UploadedAt | datetime |  |
| DeletedBy | nvarchar(256) |  |
| DeletedAt | datetime |  |
| IsDeleted | bit |  |

## 06_coaching360_app_reference

### dbo.CoachingReferenceValues

- **File:** `csv/06_coaching360_app_reference/dbo_CoachingReferenceValues.csv` (SQLite table `coaching360_app_reference__dbo_CoachingReferenceValues`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per Category x Code
- **Rows:** 78

Configurable dropdowns: coaching sources, triggers, KPI focus areas, competencies, severities, root causes, topics, tags, recognition rules, admin settings.

| Column | Source type | Notes |
|---|---|---|
| CoachingReferenceValueId | bigint identity |  |
| Category | nvarchar(80) |  |
| Code | nvarchar(80) | camelCase code stored on workflow rows |
| Label | nvarchar(200) |  |
| Description | nvarchar(1000) |  |
| SortOrder | int |  |
| IsActive | bit |  |
| NotifyOnUse | bit |  |
| MetadataJson | nvarchar(2000) |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.CompetencyBehaviors

- **File:** `csv/06_coaching360_app_reference/dbo_CompetencyBehaviors.csv` (SQLite table `coaching360_app_reference__dbo_CompetencyBehaviors`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per competency x stage x behavior
- **Rows:** 108

KFLA competency behavior catalog with behaviorally anchored rating text (copied from the app's own seed file, not synthetic).

| Column | Source type | Notes |
|---|---|---|
| CompetencyBehaviorId | bigint identity |  |
| CompetencyCode | nvarchar(80) |  |
| CompetencyName | nvarchar(200) |  |
| CompetencyDescription | nvarchar(1000) |  |
| CompetencySortOrder | int |  |
| StageNumber | int | 1-4 |
| StageName | nvarchar(120) |  |
| BehaviorNumber | int |  |
| BehaviorText | nvarchar(1000) |  |
| NeedsImprovementText | nvarchar(4000) |  |
| MeetsExpectationsText | nvarchar(4000) |  |
| ExceedsExpectationsText | nvarchar(4000) |  |
| EffectiveStartDate | datetime |  |
| EffectiveEndDate | datetime |  |
| SourceDocument | nvarchar(200) |  |
| IsActive | bit |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.KpiScoringRules

- **File:** `csv/06_coaching360_app_reference/dbo_KpiScoringRules.csv` (SQLite table `coaching360_app_reference__dbo_KpiScoringRules`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per metric x scope x effective start
- **Rows:** 26

App-owned KPI scoring rules (effective-dated). Override the legacy BranchKPI expectations when mapped.

| Column | Source type | Notes |
|---|---|---|
| KpiScoringRuleId | bigint identity |  |
| MetricCode | nvarchar(80) |  |
| MetricName | nvarchar(200) |  |
| ScoreScope | nvarchar(80) | Employee / Branch/BM / District |
| UnitOfMeasure | nvarchar(40) |  |
| GoalValue | decimal(18,4) |  |
| Weight | decimal(18,4) |  |
| ScoringDirection | nvarchar(32) |  |
| ApprovalStatus | nvarchar(32) |  |
| EffectiveStartDate | datetime |  |
| EffectiveEndDate | datetime |  |
| IsActive | bit |  |
| SourceNote | nvarchar(1000) |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.KpiScoringBands

- **File:** `csv/06_coaching360_app_reference/dbo_KpiScoringBands.csv` (SQLite table `coaching360_app_reference__dbo_KpiScoringBands`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per rule x band
- **Rows:** 105

Score bands for each rule. MaxValue NULL = open-ended.

| Column | Source type | Notes |
|---|---|---|
| KpiScoringBandId | bigint identity |  |
| KpiScoringRuleId | bigint | FK -> KpiScoringRules |
| ScoreLevel | int |  |
| Label | nvarchar(120) |  |
| MinValue | decimal(18,4) |  |
| MaxValue | decimal(18,4) |  |
| Tone | nvarchar(40) | bad / watch / good / neutral |
| SortOrder | int |  |

### dbo.KpiDefinitions

- **File:** `csv/06_coaching360_app_reference/dbo_KpiDefinitions.csv` (SQLite table `coaching360_app_reference__dbo_KpiDefinitions`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per KPI code
- **Rows:** 9

KPI catalog. Only the 9 DPR Employee Scorecard metrics are seeded.

| Column | Source type | Notes |
|---|---|---|
| KpiDefinitionId | bigint identity |  |
| KpiCode | nvarchar(80) |  |
| KpiName | nvarchar(200) |  |
| Category | nvarchar(100) |  |
| Description | nvarchar(1000) |  |
| UnitOfMeasure | nvarchar(40) |  |
| IsHigherBetter | bit |  |
| IsActive | bit |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.Employees

- **File:** `csv/06_coaching360_app_reference/dbo_Employees.csv` (SQLite table `coaching360_app_reference__dbo_Employees`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per employee
- **Rows:** 397

Directory snapshot used only for name resolution and DPR teller-id resolution. Not written by the app (loaded here so joins resolve).

| Column | Source type | Notes |
|---|---|---|
| EmployeeId | bigint identity | Internal id; DPR tables reference this |
| ExternalEmployeeId | nvarchar(64) | = UserDwid as text |
| EmployeeNumber | nvarchar(64) | = TellerID as text |
| UserPrincipalName | nvarchar(256) |  |
| DisplayName | nvarchar(200) |  |
| JobTitle | nvarchar(200) |  |
| PrimaryOrganizationalUnitId | bigint |  |
| ManagerEmployeeId | bigint | -> Employees.EmployeeId |
| IsActive | bit |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.OrganizationalUnits

- **File:** `csv/06_coaching360_app_reference/dbo_OrganizationalUnits.csv` (SQLite table `coaching360_app_reference__dbo_OrganizationalUnits`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per org node
- **Rows:** 0

Exists in the schema but is never populated; the app reads the hierarchy live from the Security API / EDA.

| Column | Source type | Notes |
|---|---|---|
| OrganizationalUnitId | bigint identity |  |
| ParentOrganizationalUnitId | bigint |  |
| UnitType | nvarchar(40) |  |
| UnitCode | nvarchar(64) |  |
| UnitName | nvarchar(200) |  |
| IsActive | bit |  |
| EffectiveStartDate | datetime |  |
| EffectiveEndDate | datetime |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.KpiScoreSnapshots

- **File:** `csv/06_coaching360_app_reference/dbo_KpiScoreSnapshots.csv` (SQLite table `coaching360_app_reference__dbo_KpiScoreSnapshots`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per KPI score snapshot
- **Rows:** 0

Exists in the schema but is never written; KPIs are read live from the source systems.

| Column | Source type | Notes |
|---|---|---|
| KpiScoreSnapshotId | bigint identity |  |
| EmployeeId | bigint |  |
| OrganizationalUnitId | bigint |  |
| KpiDefinitionId | bigint |  |
| ScorePeriodStartDate | datetime |  |
| ScorePeriodEndDate | datetime |  |
| ActualValue | decimal(18,4) |  |
| TargetValue | decimal(18,4) |  |
| ScoreValue | decimal(18,4) |  |
| RankingValue | int |  |
| RankingScope | nvarchar(80) |  |
| SourceSystem | nvarchar(80) |  |
| SourceBatchId | nvarchar(120) |  |
| CreatedUtc | datetime |  |

### dbo.Tags

- **File:** `csv/06_coaching360_app_reference/dbo_Tags.csv` (SQLite table `coaching360_app_reference__dbo_Tags`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per tag
- **Rows:** 0

Unused generic tag catalog (coaching tags live in CoachingRecords.TagCodes).

| Column | Source type | Notes |
|---|---|---|
| TagId | bigint identity |  |
| TagName | nvarchar(120) |  |
| TagType | nvarchar(80) |  |
| IsActive | bit |  |
| CreatedUtc | datetime |  |

### dbo.EntityTags

- **File:** `csv/06_coaching360_app_reference/dbo_EntityTags.csv` (SQLite table `coaching360_app_reference__dbo_EntityTags`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per entity x tag
- **Rows:** 0

Unused polymorphic tag assignment.

| Column | Source type | Notes |
|---|---|---|
| EntityTagId | bigint identity |  |
| ParentType | nvarchar(80) |  |
| ParentId | bigint |  |
| TagId | bigint |  |
| CreatedUtc | datetime |  |

### dbo.DataProtectionKeys

- **File:** `csv/06_coaching360_app_reference/dbo_DataProtectionKeys.csv` (SQLite table `coaching360_app_reference__dbo_DataProtectionKeys`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per ASP.NET data protection key
- **Rows:** 0

Framework key ring. Intentionally left empty (security material, not business data).

| Column | Source type | Notes |
|---|---|---|
| DataProtectionKeyId | bigint identity |  |
| FriendlyName | nvarchar(512) |  |
| Xml | nvarchar(max) |  |
| CreatedUtc | datetime |  |

### dbo.RolePageAccessOverrides

- **File:** `csv/06_coaching360_app_reference/dbo_RolePageAccessOverrides.csv` (SQLite table `coaching360_app_reference__dbo_RolePageAccessOverrides`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per role x page key
- **Rows:** 0

Admin overrides of the default role/page matrix. Empty by default (no overrides seeded). Valid PageKeys: home, kpis, coaching, coaching-interactions, idp, competencies, branch-visits, accountability, tasks, reporting, policy-violations, admin-center, ...

| Column | Source type | Notes |
|---|---|---|
| RolePageAccessOverrideId | bigint identity |  |
| RoleName | nvarchar(120) |  |
| PageKey | nvarchar(120) |  |
| CanAccess | bit |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| UpdatedByUserName | nvarchar(256) |  |

### dbo.PolicyViolationsModuleSettings

- **File:** `csv/06_coaching360_app_reference/dbo_PolicyViolationsModuleSettings.csv` (SQLite table `coaching360_app_reference__dbo_PolicyViolationsModuleSettings`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per ASP.NET environment
- **Rows:** 3

Per-environment toggle for the Policy Violations module; missing row = disabled.

| Column | Source type | Notes |
|---|---|---|
| EnvironmentName | nvarchar(64) | Natural PK |
| Enabled | bit |  |
| UpdatedBy | nvarchar(256) |  |
| UpdatedUtc | datetime2 |  |

### dbo.PolicyViolationsModuleAudit

- **File:** `csv/06_coaching360_app_reference/dbo_PolicyViolationsModuleAudit.csv` (SQLite table `coaching360_app_reference__dbo_PolicyViolationsModuleAudit`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per module toggle
- **Rows:** 4

Audit trail of Policy Violations module toggles.

| Column | Source type | Notes |
|---|---|---|
| Id | bigint identity |  |
| EnvironmentName | nvarchar(64) |  |
| PreviousEnabled | bit |  |
| Enabled | bit |  |
| Actor | nvarchar(256) |  |
| ChangedUtc | datetime2 |  |

## 07_coaching360_app_workflow

### dbo.CoachingRecords

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingRecords.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingRecords`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per submitted coaching record (immutable after submit)
- **Rows:** 2,414

Manager-documented coaching of an employee. KPI-triggered records cite the employee's prior-month KPI values from the BranchKPI sources.

| Column | Source type | Notes |
|---|---|---|
| CoachingRecordId | bigint identity |  |
| EmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| ManagerEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| OrganizationalUnitId | bigint | BranchDWID (not branch number) |
| CoachingDate | datetime |  |
| TriggerType | nvarchar(80) | kpi / competency / qaReview / branchVisit / accountabilityCall / recognition |
| RelatedKpiDefinitionId | bigint | Always NULL |
| CompetencyCode | nvarchar(80) |  |
| Severity | nvarchar(40) |  |
| CoachingSource | nvarchar(80) |  |
| ObservationSummary | nvarchar(2000) |  |
| SpecificExample | nvarchar(2000) |  |
| CoachingProvided | nvarchar(4000) |  |
| EmployeeResponse | nvarchar(4000) |  |
| RootCause | nvarchar(2000) |  |
| ActionRequired | nvarchar(2000) |  |
| OwnerType | nvarchar(40) |  |
| DueDate | datetime |  |
| FollowUpDate | datetime |  |
| Status | nvarchar(60) | Submitted / PendingAcknowledgement |
| VisibleToEmployee | bit |  |
| AcknowledgementRequired | bit |  |
| AcknowledgedUtc | datetime |  |
| EscalationRequired | bit |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| TriggerReason | nvarchar(160) |  |
| KpiFocusCode | nvarchar(120) |  |
| ExpectationClarified | bit |  |
| TrainingJobAidReference | nvarchar(1000) |  |
| SubmittedUtc | datetime |  |
| SubmittedByUserName | nvarchar(256) |  |
| TopicCode | nvarchar(80) |  |
| TagCodes | nvarchar(500) | Comma-joined tag codes |

### dbo.CoachingRecordAcknowledgements

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingRecordAcknowledgements.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingRecordAcknowledgements`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** At most one per coaching record x employee
- **Rows:** 1,142

Employee acknowledgement of a coaching record.

| Column | Source type | Notes |
|---|---|---|
| CoachingRecordAcknowledgementId | bigint identity |  |
| CoachingRecordId | bigint |  |
| EmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| AcknowledgedByUserName | nvarchar(256) |  |
| Comment | nvarchar(4000) |  |
| AcknowledgedUtc | datetime |  |

### dbo.CoachingInteractions

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingInteractions.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingInteractions`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per comment on a coaching record
- **Rows:** 2,368

Employee-visible or internal (manager-only) comments appended after submit.

| Column | Source type | Notes |
|---|---|---|
| CoachingInteractionId | bigint identity |  |
| CoachingRecordId | bigint |  |
| AuthorEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| InteractionType | nvarchar(80) | EmployeeComment / InternalComment |
| Body | nvarchar(4000) |  |
| IsInternal | bit |  |
| CreatedUtc | datetime |  |
| AuthorUserName | nvarchar(256) |  |

### dbo.IndividualDevelopmentGoals

- **File:** `csv/07_coaching360_app_workflow/dbo_IndividualDevelopmentGoals.csv` (SQLite table `coaching360_app_workflow__dbo_IndividualDevelopmentGoals`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One non-archived plan per employee per month
- **Rows:** 1,621

Monthly Success Plans (IDPs). Lifecycle Active -> Approved -> Locked (manual or system auto-finalize) -> Archived. MonthlyKpiGoals is JSON built from KPI actuals.

| Column | Source type | Notes |
|---|---|---|
| IndividualDevelopmentGoalId | bigint identity |  |
| EmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| ManagerEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| RelatedCoachingRecordId | bigint |  |
| GoalMonth | datetime | First of month |
| DevelopmentArea | nvarchar(160) |  |
| GoalStatement | nvarchar(2000) |  |
| ActionPlan | nvarchar(4000) |  |
| Status | nvarchar(60) | Active / Approved / Locked / Archived |
| DueDate | datetime |  |
| CompletedUtc | datetime |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| FocusType | nvarchar(40) | KPI / Competency / MetricCompetency |
| Strengths | nvarchar(2000) |  |
| Opportunities | nvarchar(2000) |  |
| SuccessMeasures | nvarchar(2000) |  |
| MonthlyContinue | nvarchar(2000) |  |
| MonthlyImprove | nvarchar(2000) |  |
| CreatedByUserName | nvarchar(256) |  |
| UpdatedByUserName | nvarchar(256) |  |
| ApprovedUtc | datetime |  |
| ApprovedByUserName | nvarchar(256) |  |
| LockedUtc | datetime |  |
| LockedByUserName | nvarchar(256) | 'system' when auto-finalized |
| IsArchived | bit |  |
| ArchivedUtc | datetime |  |
| ArchivedByUserName | nvarchar(256) |  |
| PdfGeneratedUtc | datetime |  |
| PdfGeneratedByUserName | nvarchar(256) |  |
| DayforceExportStatus | nvarchar(80) |  |
| MetricFocusAreas | nvarchar(1000) | JSON array of labels |
| CompetencyFocusAreas | nvarchar(1000) | JSON array of labels |
| MonthlyKpiGoals | nvarchar(4000) | JSON array: metricKey, metricLabel, previous/current actual+goal, ytdAverage, goalValue |
| EmployeeDisplayName | nvarchar(256) |  |

### dbo.IndividualDevelopmentGoalComments

- **File:** `csv/07_coaching360_app_workflow/dbo_IndividualDevelopmentGoalComments.csv` (SQLite table `coaching360_app_workflow__dbo_IndividualDevelopmentGoalComments`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per Success Plan comment
- **Rows:** 1,747

Comment thread on a Success Plan.

| Column | Source type | Notes |
|---|---|---|
| IndividualDevelopmentGoalCommentId | bigint identity |  |
| IndividualDevelopmentGoalId | bigint |  |
| AuthorEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| AuthorUserName | nvarchar(256) |  |
| Body | nvarchar(4000) |  |
| CreatedUtc | datetime |  |

### dbo.AccountabilityMeetings

- **File:** `csv/07_coaching360_app_workflow/dbo_AccountabilityMeetings.csv` (SQLite table `coaching360_app_workflow__dbo_AccountabilityMeetings`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per accountability meeting
- **Rows:** 1,471

Weekly accountability meetings (DM with BMs; BM with branch staff). Draft -> Finalized.

| Column | Source type | Notes |
|---|---|---|
| AccountabilityMeetingId | bigint identity |  |
| OwnerEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| OrganizationalUnitId | bigint | BranchDWID; NULL for multi-branch DM meetings |
| MeetingDate | datetime |  |
| Subject | nvarchar(240) |  |
| Summary | nvarchar(4000) |  |
| Status | nvarchar(60) | Draft / Finalized |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.AccountabilityMeetingParticipants

- **File:** `csv/07_coaching360_app_workflow/dbo_AccountabilityMeetingParticipants.csv` (SQLite table `coaching360_app_workflow__dbo_AccountabilityMeetingParticipants`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per meeting x participant
- **Rows:** 6,031

Per-participant notes, focus metrics, and plan of action (non-blank plan -> task on finalize).

| Column | Source type | Notes |
|---|---|---|
| AccountabilityMeetingParticipantId | bigint identity |  |
| AccountabilityMeetingId | bigint |  |
| EmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| DiscussionNotes | nvarchar(4000) |  |
| FocusMetricsAndGoals | nvarchar(4000) |  |
| PlanOfAction | nvarchar(4000) |  |
| PreviousCommitments | nvarchar(4000) |  |
| StatusUpdate | nvarchar(4000) |  |

### dbo.BranchVisitPlanningPlaceholders

- **File:** `csv/07_coaching360_app_workflow/dbo_BranchVisitPlanningPlaceholders.csv` (SQLite table `coaching360_app_workflow__dbo_BranchVisitPlanningPlaceholders`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per planned visit (leader x branch x date)
- **Rows:** 816

Calendar plan entries. Active = planned, Converted = visit started, Removed = cancelled.

| Column | Source type | Notes |
|---|---|---|
| BranchVisitPlanningPlaceholderId | bigint identity |  |
| OrganizationalUnitId | bigint | BranchDWID |
| VisitDate | datetime |  |
| CreatedByUserName | nvarchar(256) |  |
| CreatedByDisplayName | nvarchar(256) |  |
| Status | nvarchar(40) | Active / Converted / Removed |
| ConvertedBranchVisitId | bigint |  |
| RemovedUtc | datetime |  |
| RemovedByUserName | nvarchar(256) |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| IsConfidentialVisit | bit |  |

### dbo.BranchVisits

- **File:** `csv/07_coaching360_app_workflow/dbo_BranchVisits.csv` (SQLite table `coaching360_app_workflow__dbo_BranchVisits`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per branch visit report
- **Rows:** 711

Branch visit after-action reviews by DMs and RVPs. Confidential visits hide leadership feedback from the BM.

| Column | Source type | Notes |
|---|---|---|
| BranchVisitId | bigint identity |  |
| OrganizationalUnitId | bigint | BranchDWID |
| VisitDate | datetime |  |
| VisitStatus | nvarchar(60) | Draft / Submitted |
| VisitPurpose | nvarchar(1000) |  |
| ConfidentialLeadershipFeedback | nvarchar(4000) |  |
| SubmittedUtc | datetime |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| SubmittedByUserName | nvarchar(256) | Holds the submitter's display name |
| IsArchived | bit |  |
| ArchivedUtc | datetime |  |
| ArchivedByUserName | nvarchar(256) |  |
| IsConfidentialVisit | bit |  |

### dbo.BranchVisitTopics

- **File:** `csv/07_coaching360_app_workflow/dbo_BranchVisitTopics.csv` (SQLite table `coaching360_app_workflow__dbo_BranchVisitTopics`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per visit x topic
- **Rows:** 3,375

Discussion topics (3 mandatory + optional) with notes and optional follow-up action.

| Column | Source type | Notes |
|---|---|---|
| BranchVisitTopicId | bigint identity |  |
| BranchVisitId | bigint |  |
| TopicCode | nvarchar(80) |  |
| TopicTitle | nvarchar(200) |  |
| IsMandatory | bit |  |
| DiscussionNotes | nvarchar(4000) |  |
| FollowUpRequired | bit |  |
| ActionPlan | nvarchar(4000) |  |
| AssignedOwnerName | nvarchar(256) |  |
| DueDate | datetime |  |
| AssignedOwnerEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |

### dbo.CoachingTasks

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingTasks.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingTasks`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per task / action item
- **Rows:** 7,846

Action items from coaching records, branch visits, and accountability meetings, plus coaching acknowledgement tasks.

| Column | Source type | Notes |
|---|---|---|
| CoachingTaskId | bigint identity |  |
| ParentType | nvarchar(80) | CoachingRecord / BranchVisit / AccountabilityMeeting |
| ParentId | bigint |  |
| AssignedToEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| Subject | nvarchar(240) |  |
| Body | nvarchar(4000) |  |
| Severity | nvarchar(40) |  |
| DueDate | datetime |  |
| CompletedUtc | datetime |  |
| Status | nvarchar(60) | Open / In Progress / Completed / Escalated |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |
| OwnerName | nvarchar(256) |  |
| FollowUpType | nvarchar(80) | Acknowledgement / Task / Meeting / Reminder / Accountability Action |
| FollowUpDate | datetime |  |
| AcknowledgementRequired | bit | Retired; always 0 |
| AcknowledgedUtc | datetime |  |
| AcknowledgedByEmployeeId | bigint |  |
| AcknowledgedByUserName | nvarchar(256) |  |
| AcknowledgementComment | nvarchar(1000) |  |
| CreatedByUserName | nvarchar(256) |  |

### dbo.CoachingNotifications

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingNotifications.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingNotifications`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per recipient per event
- **Rows:** 31,878

In-app notifications.

| Column | Source type | Notes |
|---|---|---|
| CoachingNotificationId | bigint identity |  |
| RecipientEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| RecipientUserName | nvarchar(256) |  |
| RecipientDisplayName | nvarchar(256) |  |
| EventType | nvarchar(100) |  |
| Title | nvarchar(240) |  |
| Body | nvarchar(2000) |  |
| ParentType | nvarchar(80) |  |
| ParentId | bigint |  |
| ActionUrl | nvarchar(500) |  |
| Severity | nvarchar(40) |  |
| DeduplicationKey | nvarchar(240) |  |
| CreatedUtc | datetime |  |
| CreatedByUserName | nvarchar(256) |  |
| ReadUtc | datetime |  |
| ReadByUserName | nvarchar(256) |  |

### dbo.CoachingNotificationDeliveries

- **File:** `csv/07_coaching360_app_workflow/dbo_CoachingNotificationDeliveries.csv` (SQLite table `coaching360_app_workflow__dbo_CoachingNotificationDeliveries`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per notification x channel attempt
- **Rows:** 63,756

Delivery log. Email is disabled in non-production configuration, so Email rows are Queued.

| Column | Source type | Notes |
|---|---|---|
| CoachingNotificationDeliveryId | bigint identity |  |
| CoachingNotificationId | bigint |  |
| Channel | nvarchar(40) | InApp / Email / SupportAlert |
| Status | nvarchar(60) | Queued / Sent / Skipped / Failed |
| Detail | nvarchar(2000) |  |
| AttemptCount | int |  |
| LastAttemptUtc | datetime |  |
| CreatedUtc | datetime |  |

### dbo.AttachmentReferences

- **File:** `csv/07_coaching360_app_workflow/dbo_AttachmentReferences.csv` (SQLite table `coaching360_app_workflow__dbo_AttachmentReferences`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per uploaded file
- **Rows:** 157

File attachments. Binary Content is omitted from the demo dataset (NULL); ContentBytes gives a plausible size.

| Column | Source type | Notes |
|---|---|---|
| AttachmentReferenceId | bigint identity |  |
| ParentType | nvarchar(80) | CoachingRecord / BranchVisit / RolloutFeedback |
| ParentId | bigint |  |
| FileName | nvarchar(260) |  |
| ContentType | nvarchar(160) |  |
| StorageKey | nvarchar(500) |  |
| UploadedByEmployeeId | bigint | UserDwid of the person (not Employees.EmployeeId) |
| UploadedUtc | datetime |  |
| Content | varbinary(max) | Omitted (NULL) |
| ContentBytes | int | Synthetic convenience column; not in the app schema |

### dbo.KpiReviewMonthExclusions

- **File:** `csv/07_coaching360_app_workflow/dbo_KpiReviewMonthExclusions.csv` (SQLite table `coaching360_app_workflow__dbo_KpiReviewMonthExclusions`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per employee x branch x review month
- **Rows:** 12

Employee months excluded from KPI review averages (with required comment).

| Column | Source type | Notes |
|---|---|---|
| KpiReviewMonthExclusionId | bigint identity |  |
| ScopeType | nvarchar(40) |  |
| BranchNumber | int |  |
| DistrictNumber | int |  |
| EmployeeIdentifier | nvarchar(160) | Lower-case login |
| EmployeeName | nvarchar(200) |  |
| ReviewMonth | datetime |  |
| IsExcluded | bit |  |
| ExclusionComment | nvarchar(2000) |  |
| CreatedByUserName | nvarchar(256) |  |
| CreatedUtc | datetime |  |
| UpdatedByUserName | nvarchar(256) |  |
| UpdatedUtc | datetime |  |

### dbo.RolloutFeedbackItems

- **File:** `csv/07_coaching360_app_workflow/dbo_RolloutFeedbackItems.csv` (SQLite table `coaching360_app_workflow__dbo_RolloutFeedbackItems`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per feedback submission
- **Rows:** 48

In-app rollout/UAT feedback with admin triage.

| Column | Source type | Notes |
|---|---|---|
| RolloutFeedbackItemId | bigint identity |  |
| FeedbackType | nvarchar(64) | Feedback / Defect / EnhancementRequest / QuestionBlocker |
| Status | nvarchar(40) | New / Reviewing / TicketCreated / Closed |
| Summary | nvarchar(160) |  |
| Details | nvarchar(4000) |  |
| Impact | nvarchar(1000) |  |
| PageUrl | nvarchar(2048) |  |
| SubmitterEmployeeId | bigint | Always NULL |
| SubmitterUserName | nvarchar(256) |  |
| SubmitterDisplayName | nvarchar(256) |  |
| SubmitterTitle | nvarchar(200) |  |
| SubmitterRoles | nvarchar(500) |  |
| SubmitterAccessScope | nvarchar(120) |  |
| SubmittedUtc | datetime |  |
| AdminNotes | nvarchar(2000) | Legacy |
| FollowUpReference | nvarchar(240) | Jira key |
| UpdatedByUserName | nvarchar(256) |  |
| UpdatedUtc | datetime |  |
| TestCaseId | nvarchar(120) |  |
| ExpectedResult | nvarchar(2000) |  |
| ActualResult | nvarchar(2000) |  |

### dbo.RolloutFeedbackAdminNotes

- **File:** `csv/07_coaching360_app_workflow/dbo_RolloutFeedbackAdminNotes.csv` (SQLite table `coaching360_app_workflow__dbo_RolloutFeedbackAdminNotes`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per admin triage note
- **Rows:** 80

Admin notes on rollout feedback.

| Column | Source type | Notes |
|---|---|---|
| RolloutFeedbackAdminNoteId | bigint identity |  |
| RolloutFeedbackItemId | bigint |  |
| Body | nvarchar(2000) |  |
| CreatedByUserName | nvarchar(256) |  |
| CreatedUtc | datetime |  |

### dbo.AuditEvents

- **File:** `csv/07_coaching360_app_workflow/dbo_AuditEvents.csv` (SQLite table `coaching360_app_workflow__dbo_AuditEvents`)
- **Source system:** Coaching360 application database (dbo)
- **Grain:** One row per workflow action
- **Rows:** 32,102

Append-only audit trail for every workflow action (sorted by time).

| Column | Source type | Notes |
|---|---|---|
| AuditEventId | bigint identity |  |
| EntityType | nvarchar(80) |  |
| EntityId | bigint |  |
| ActionName | nvarchar(80) |  |
| PerformedBy | nvarchar(256) |  |
| PerformedUtc | datetime |  |
| SummaryJson | nvarchar(4000) |  |

## 08_coaching360_app_dpr

### dbo.DprScorecardEtlBatches

- **File:** `csv/08_coaching360_app_dpr/dbo_DprScorecardEtlBatches.csv` (SQLite table `coaching360_app_dpr__dbo_DprScorecardEtlBatches`)
- **Source system:** Coaching360 application database (dbo) (loaded by external python_etl job)
- **Grain:** One row per daily ETL run
- **Rows:** 292

DPR Employee Scorecard ETL runs (daily, incremental window = previous + current month). Mostly Published, occasional Failed.

| Column | Source type | Notes |
|---|---|---|
| DprScorecardEtlBatchId | bigint identity |  |
| BatchIdentifier | uniqueidentifier |  |
| JobName | nvarchar(120) |  |
| LoadType | nvarchar(40) |  |
| Status | nvarchar(32) | Started / Validated / Published / Failed |
| SourceSystem | nvarchar(160) |  |
| SourceQueryVersion | nvarchar(80) |  |
| SourcePeriodStartDate | datetime |  |
| SourcePeriodEndDate | datetime |  |
| SourceFreshnessUtc | datetime |  |
| ExtractedRowCount | int |  |
| StagedRowCount | int |  |
| PublishedRowCount | int |  |
| RejectedRowCount | int |  |
| StartedUtc | datetime |  |
| CompletedUtc | datetime |  |
| FailureDetail | nvarchar(4000) |  |

### dbo.DprEmployeeScorecardMetrics

- **File:** `csv/08_coaching360_app_dpr/dbo_DprEmployeeScorecardMetrics.csv` (SQLite table `coaching360_app_dpr__dbo_DprEmployeeScorecardMetrics`)
- **Source system:** Coaching360 application database (dbo) (loaded by external python_etl job)
- **Grain:** One row per teller x month-end x metric
- **Rows:** 18,243

Published DPR metrics for Account Representatives / Assistant Branch Managers. Ratios are fractions.

| Column | Source type | Notes |
|---|---|---|
| DprEmployeeScorecardMetricId | bigint identity |  |
| EmployeeId | bigint | FK -> Employees.EmployeeId (internal id, not UserDwid) |
| KpiDefinitionId | bigint | FK -> KpiDefinitions |
| MetricMonthEndDate | datetime | EOMONTH |
| MetricValue | decimal(19,8) |  |
| ValueStatus | nvarchar(32) | Available / NotCalculated / SourceUnavailable |
| SourceTellerId | nvarchar(64) |  |
| SourceSystem | nvarchar(160) |  |
| PublishedByBatchId | bigint | FK -> DprScorecardEtlBatches |
| SourceFreshnessUtc | datetime |  |
| CreatedUtc | datetime |  |
| UpdatedUtc | datetime |  |

### dbo.DprScorecardMetricStaging

- **File:** `csv/08_coaching360_app_dpr/dbo_DprScorecardMetricStaging.csv` (SQLite table `coaching360_app_dpr__dbo_DprScorecardMetricStaging`)
- **Source system:** Coaching360 application database (dbo) (loaded by external python_etl job)
- **Grain:** One row per batch x source row x metric
- **Rows:** 7,326

Staging rows with validation outcome. Only the two most recent successful batches are included to keep the demo small.

| Column | Source type | Notes |
|---|---|---|
| DprScorecardMetricStagingId | bigint identity |  |
| DprScorecardEtlBatchId | bigint |  |
| SourceRowNumber | int |  |
| SourceTellerId | nvarchar(64) |  |
| SourceEmployeeName | nvarchar(200) |  |
| EmployeeId | bigint |  |
| MetricMonthEndDate | datetime |  |
| MetricCode | nvarchar(80) |  |
| SourceMetricName | nvarchar(160) |  |
| MetricValue | decimal(19,8) |  |
| ValueStatus | nvarchar(32) |  |
| ValidationStatus | nvarchar(32) | Pending / Valid / Rejected |
| ValidationDetail | nvarchar(2000) |  |
| SourceSystem | nvarchar(160) |  |
| SourcePayloadJson | nvarchar(4000) |  |
| CreatedUtc | datetime |  |

### dbo.DprScorecardMetricRejections

- **File:** `csv/08_coaching360_app_dpr/dbo_DprScorecardMetricRejections.csv` (SQLite table `coaching360_app_dpr__dbo_DprScorecardMetricRejections`)
- **Source system:** Coaching360 application database (dbo) (loaded by external python_etl job)
- **Grain:** One row per rejected staging row
- **Rows:** 18

Rejected DPR rows (InvalidIdentity | DuplicateOrInvalidPeriod).

| Column | Source type | Notes |
|---|---|---|
| DprScorecardMetricRejectionId | bigint identity |  |
| DprScorecardEtlBatchId | bigint |  |
| SourceRowNumber | int |  |
| SourceTellerId | nvarchar(64) |  |
| SourceEmployeeName | nvarchar(200) |  |
| EmployeeId | bigint |  |
| MetricMonthEndDate | datetime |  |
| MetricCode | nvarchar(80) |  |
| RejectionCode | nvarchar(80) |  |
| RejectionDetail | nvarchar(2000) |  |
| SourcePayloadJson | nvarchar(4000) |  |
| CreatedUtc | datetime |  |
