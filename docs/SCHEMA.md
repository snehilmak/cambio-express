# Database schema map

> **Generated** by `python -m scripts.dump_schema_doc` from the SQLAlchemy models. Do not edit by hand — `tests/Core/test_table_prefixes.py` fails when this file is stale.

Every table is named `<area>_<thing>`. The prefix says which part of the product owns it; whether a row is pinned to one store is on the row itself as `store_id`. Convention and module map: `api/Core/Schema.py`.

## Areas

| Prefix | What belongs there | Modules |
|---|---|---|
| `tenancy_` | Who exists: stores, users, employees, owner links, roles. The rows everything else points at. | Tenancy |
| `auth_` | Credentials and sessions. Governed by Auth/INVARIANTS.md; changes need the security-review header. | Auth |
| `billing_` | Plans, feature flags, discounts, referrals. Stripe is the counterpart. | Billing, FeatureFlags |
| `platform_` | Superadmin-owned, no store: settings, webhook ingest, announcements, push. | Announcements, Superadmin, Webhooks |
| `support_` | Tickets between a store and the platform. | Support |
| `audit_` | Append-only history. Never edited, never purged early. | Audit |
| `bank_` | Bank feed via Stripe Financial Connections. Shared across product lines. | BankSync |
| `hr_` | Time clock now, payroll later. People-hours, not money. | TimeClock |
| `msb_` | Remittance money: transfers, senders, ACH batches, the MSB daily book, monthly P&L, returned checks, the rate board. | Batches, Customers, DailyBook, Monthly, ReturnChecks, TVDisplay, Transfers |
| `retail_` | C-store money: registers, departments, the Store daily book, lottery, POS journal ingest, price book, vendors, purchases. | Catalog, DayClose, Lottery, PosImport, StoreBook |

Library-owned, not renamed: `alembic_version`, `casbin_rule`.

## `tenancy_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `tenancy_owner_connect_code` | `OwnerConnectCode` | `Tenancy` | owner | `tenancy_store.id`, `tenancy_user.id` | — |
| `tenancy_store` | `Store` | `Tenancy` | global | `billing_referral_code.id` | — |
| `tenancy_store_employee` | `StoreEmployee` | `Tenancy` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `tenancy_store_owner_link` | `StoreOwnerLink` | `Tenancy` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `tenancy_store_role` | `StoreRole` | `Tenancy` | store | `tenancy_store.id` | — |
| `tenancy_store_role_permission` | `StoreRolePermission` | `Tenancy` | store | `tenancy_store.id`, `tenancy_store_role.id` | — |
| `tenancy_user` | `User` | `Tenancy` | store | `tenancy_store.id`, `tenancy_store_role.id` | — |

## `auth_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `auth_login_event` | `LoginEvent` | `Auth` | user | `tenancy_user.id` | [INVARIANTS](../api/Modules/Auth/INVARIANTS.md) |
| `auth_passkey` | `Passkey` | `Auth` | user | `tenancy_user.id` | [INVARIANTS](../api/Modules/Auth/INVARIANTS.md) |
| `auth_password_reset_token` | `PasswordResetToken` | `Auth` | user | `tenancy_user.id` | [INVARIANTS](../api/Modules/Auth/INVARIANTS.md) |
| `auth_recovery_code` | `RecoveryCode` | `Auth` | user | `tenancy_user.id` | [INVARIANTS](../api/Modules/Auth/INVARIANTS.md) |
| `auth_refresh_token` | `RefreshToken` | `Auth` | user | `auth_refresh_token.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/Auth/INVARIANTS.md) |

## `billing_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `billing_discount_code` | `DiscountCode` | `Billing` | global | `tenancy_user.id` | — |
| `billing_feature_flag` | `FeatureFlag` | `Billing` | global | — | — |
| `billing_referral_code` | `ReferralCode` | `Billing` | global | `tenancy_store.id` | — |
| `billing_referral_redemption` | `ReferralRedemption` | `Billing` | billing_referral_code (FK) | `billing_referral_code.id`, `tenancy_store.id` | — |
| `billing_store_feature_override` | `StoreFeatureOverride` | `Billing` | store | `tenancy_store.id`, `tenancy_user.id` | — |

## `platform_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `platform_announcement` | `Announcement` | `Announcements` | global | `tenancy_user.id` | — |
| `platform_announcement_store` | `AnnouncementStore` | `Announcements` | store | `platform_announcement.id`, `tenancy_store.id` | — |
| `platform_email_event` | `EmailEvent` | `Webhooks` | user | `tenancy_user.id` | — |
| `platform_push_subscription` | `PushSubscription` | `Announcements` | user | `tenancy_user.id` | — |
| `platform_setting` | `PlatformSetting` | `Superadmin` | global | — | — |
| `platform_webhook_event` | `WebhookEvent` | `Webhooks` | global | — | — |

## `support_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `support_message` | `SupportMessage` | `Support` | store | `support_ticket.id`, `tenancy_store.id`, `tenancy_user.id` | — |
| `support_ticket` | `SupportTicket` | `Support` | store | `tenancy_store.id`, `tenancy_user.id` | — |

## `audit_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `audit_operator_log` | `OperatorAuditLog` | `Audit` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `audit_owner_log` | `OwnerAuditLog` | `Audit` | owner | `tenancy_user.id` | — |
| `audit_superadmin_log` | `SuperadminAuditLog` | `Audit` | global | `tenancy_user.id` | — |
| `audit_transfer` | `TransferAudit` | `Audit` | store | `msb_transfer.id`, `tenancy_store.id`, `tenancy_store_employee.id`, `tenancy_user.id` | — |

## `bank_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `bank_rule` | `BankRule` | `BankSync` | store | `bank_stripe_account.id`, `tenancy_store.id` | — |
| `bank_stripe_account` | `StripeBankAccount` | `BankSync` | store | `tenancy_store.id` | — |
| `bank_transaction` | `BankTransaction` | `BankSync` | store | `bank_stripe_account.id`, `msb_daily_line_item.id`, `tenancy_store.id` | — |

## `hr_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `hr_store_employee_passkey` | `StoreEmployeePasskey` | `TimeClock` | store | `tenancy_store.id`, `tenancy_store_employee.id`, `tenancy_user.id` | — |
| `hr_time_clock_entry` | `TimeClockEntry` | `TimeClock` | store | `tenancy_store.id`, `tenancy_store_employee.id`, `tenancy_user.id` | — |
| `hr_time_clock_shift` | `TimeClockShift` | `TimeClock` | store | `tenancy_store.id`, `tenancy_store_employee.id`, `tenancy_user.id` | — |

## `msb_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `msb_ach_batch` | `ACHBatch` | `Batches` | store | `tenancy_store.id` | — |
| `msb_check_deposit` | `CheckDeposit` | `DailyBook` | store | `tenancy_store.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/DailyBook/INVARIANTS.md) |
| `msb_customer` | `Customer` | `Customers` | store | `tenancy_store.id` | — |
| `msb_daily_drop` | `DailyDrop` | `DailyBook` | store | `tenancy_store.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/DailyBook/INVARIANTS.md) |
| `msb_daily_line_item` | `DailyLineItem` | `DailyBook` | store | `msb_return_check.id`, `tenancy_store.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/DailyBook/INVARIANTS.md) |
| `msb_daily_report` | `DailyReport` | `DailyBook` | store | `tenancy_store.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/DailyBook/INVARIANTS.md) |
| `msb_monthly_financial` | `MonthlyFinancial` | `Monthly` | store | `tenancy_store.id` | [INVARIANTS](../api/Modules/Monthly/INVARIANTS.md) |
| `msb_mt_summary` | `MoneyTransferSummary` | `DailyBook` | store | `tenancy_store.id` | [INVARIANTS](../api/Modules/DailyBook/INVARIANTS.md) |
| `msb_return_check` | `ReturnCheck` | `ReturnChecks` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `msb_return_check_payment` | `ReturnCheckPayment` | `ReturnChecks` | msb_return_check (FK) | `msb_return_check.id`, `tenancy_user.id` | — |
| `msb_transfer` | `Transfer` | `Transfers` | store | `msb_customer.id`, `tenancy_store.id`, `tenancy_store_employee.id`, `tenancy_user.id` | [INVARIANTS](../api/Modules/Transfers/INVARIANTS.md) |
| `msb_tv_bank_catalog` | `TVBankCatalog` | `TVDisplay` | global | — | — |
| `msb_tv_catalog_logo` | `TVCatalogLogo` | `TVDisplay` | global | — | — |
| `msb_tv_company_catalog` | `TVCompanyCatalog` | `TVDisplay` | global | — | — |
| `msb_tv_display` | `TVDisplay` | `TVDisplay` | store | `tenancy_store.id` | — |
| `msb_tv_display_country` | `TVDisplayCountry` | `TVDisplay` | msb_tv_display (FK) | `msb_tv_display.id` | — |
| `msb_tv_display_payout_bank` | `TVDisplayPayoutBank` | `TVDisplay` | msb_tv_display_country (FK) | `msb_tv_display_country.id` | — |
| `msb_tv_display_rate` | `TVDisplayRate` | `TVDisplay` | msb_tv_display_payout_bank (FK) | `msb_tv_display_payout_bank.id` | — |
| `msb_tv_pairing` | `TVPairing` | `TVDisplay` | msb_tv_display (FK) | `msb_tv_display.id` | — |
| `msb_tv_pending_pair` | `TVPendingPair` | `TVDisplay` | msb_tv_pairing (FK) | `msb_tv_pairing.id` | — |

## `retail_`

| Table | Model | Module | Scope | Foreign keys | Read first |
|---|---|---|---|---|---|
| `retail_department` | `Department` | `DayClose` | store | `retail_department.id`, `tenancy_store.id` | — |
| `retail_department_sale` | `DepartmentSale` | `DayClose` | store | `retail_department.id`, `retail_register_close.id`, `tenancy_store.id` | — |
| `retail_hourly_sale` | `HourlySale` | `DayClose` | store | `tenancy_store.id` | — |
| `retail_lottery_day_count` | `LotteryDayCount` | `Lottery` | store | `retail_lottery_pack.id`, `tenancy_store.id`, `tenancy_user.id` | — |
| `retail_lottery_game` | `LotteryGame` | `Lottery` | store | `tenancy_store.id` | — |
| `retail_lottery_pack` | `LotteryPack` | `Lottery` | store | `retail_lottery_game.id`, `tenancy_store.id`, `tenancy_user.id` | — |
| `retail_pos_agent_credential` | `PosAgentCredential` | `PosImport` | store | `tenancy_store.id` | — |
| `retail_pos_item_day_sale` | `PosItemDaySale` | `PosImport` | store | `tenancy_store.id` | — |
| `retail_pos_journal_file` | `PosJournalFile` | `PosImport` | store | `tenancy_store.id` | — |
| `retail_pos_merchandise_map` | `PosMerchandiseMap` | `PosImport` | store | `retail_department.id`, `tenancy_store.id` | — |
| `retail_pos_transaction` | `PosTransaction` | `PosImport` | store | `tenancy_store.id` | — |
| `retail_pos_transaction_line` | `PosTransactionLine` | `PosImport` | store | `retail_pos_transaction.id` | — |
| `retail_pos_transaction_tender` | `PosTransactionTender` | `PosImport` | store | `retail_pos_transaction.id` | — |
| `retail_price_book_item` | `PriceBookItem` | `Catalog` | store | `retail_department.id`, `retail_vendor.id`, `tenancy_store.id` | — |
| `retail_purchase_invoice` | `PurchaseInvoice` | `Catalog` | store | `retail_vendor.id`, `tenancy_store.id`, `tenancy_user.id` | — |
| `retail_purchase_invoice_line` | `PurchaseInvoiceLine` | `Catalog` | store | `retail_price_book_item.id`, `retail_purchase_invoice.id`, `tenancy_store.id` | — |
| `retail_register_close` | `RegisterClose` | `DayClose` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `retail_store_daily_entry` | `StoreDailyEntry` | `StoreBook` | store | `tenancy_store.id`, `tenancy_user.id` | — |
| `retail_store_daily_entry_original` | `StoreDailyEntryOriginal` | `StoreBook` | store | `retail_store_daily_entry.id` | — |
| `retail_vendor` | `Vendor` | `Catalog` | store | `tenancy_store.id` | — |
