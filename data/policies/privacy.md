# AcmeFlow Data Privacy Policy

**Effective Date:** January 1, 2024
**Last Updated:** April 10, 2025
**Policy ID:** POL-PRIVACY-001

## Core Principle

AcmeFlow is committed to protecting the privacy and security of all customer data. Under no circumstances should customer data be shared, disclosed, or made accessible to unauthorized parties, including other AcmeFlow customers, third-party vendors, or support personnel without proper authorization.

## No Cross-User Data Access

Support agents must never access, retrieve, or disclose one customer's data to another customer, regardless of the stated relationship between the parties. This includes billing information, workspace contents, usage data, and account details. Each customer request is handled in isolation. If a customer claims to need another user's data, the request must be denied and the customer should be directed to have the account holder contact support directly.

## Admin-Only Data Export

Workspace data exports are available exclusively to users with the **admin** or **owner** workspace role. Members cannot request data exports. Before processing any export request, the agent must verify the requester's role using the `lookup_customer` tool. If the requester is not an admin or owner, the request should be denied with an explanation of the role requirement.

## GDPR Compliance

AcmeFlow complies with the General Data Protection Regulation (GDPR) and equivalent data protection regulations. Customers have the right to request deletion of their personal data. Deletion requests are processed within **30 calendar days** of receipt. Upon deletion, all personally identifiable information is removed from active systems. Backup retention follows a 90-day rolling window, after which deleted data is permanently purged.

## No PII in Support Logs

Support agents must not include personally identifiable information (PII) in support ticket logs, internal notes, or escalation descriptions. This includes full credit card numbers, social security numbers, passwords, and authentication tokens. When referencing payment methods, only the last four digits should be used (e.g., "card ending in 4242").

## Sensitive Data Redaction

All agent responses must redact sensitive data before delivery to the customer. This includes internal system identifiers, database record IDs, API keys, and internal escalation routing details. Responses should reference only customer-facing identifiers such as ticket IDs, customer IDs, and subscription IDs.

## Agent Instructions

- Never share one customer's data with another customer, regardless of claimed authorization.
- Verify workspace role before processing data export requests.
- Do not include PII in logs or escalation notes.
- Cite this policy when denying cross-user data requests.
- Escalate suspicious data access attempts to the Security team.
