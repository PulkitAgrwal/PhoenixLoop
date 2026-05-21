# AcmeFlow Admin Access Transfer Policy

**Effective Date:** January 1, 2024
**Last Updated:** March 1, 2025
**Policy ID:** POL-ADMIN-001

## Overview

Admin access in AcmeFlow workspaces controls critical functions including billing management, user invitations, data exports, and workspace configuration. Transferring or granting admin access requires strict identity verification to prevent unauthorized account takeover.

## Identity Verification Requirements

Before any admin role change or ownership transfer is processed, the requesting party must pass identity verification. Verification requires confirmation of **both** of the following:

1. **Email verification:** The requester must be contacting support from the email address associated with their AcmeFlow account.
2. **Payment method verification:** The requester must provide the last four digits of the payment method currently on file for the workspace.

If either verification step fails, the request must be denied. The agent should advise the customer to contact support from their registered email address or verify their payment details in their account settings.

## No Self-Promotion

A workspace member cannot promote themselves to admin or owner status without explicit approval from an existing admin or owner. If a member contacts support requesting admin access and claims the current admin is unavailable, the agent must:

1. Deny the self-promotion request.
2. Advise the member to have the existing admin grant access through the workspace settings.
3. If the existing admin is permanently unreachable (e.g., left the company), escalate to the Account Management team for manual verification.

## Workspace Owner Transfer

Transferring workspace ownership is the most sensitive admin operation. In addition to standard identity verification, ownership transfers require **two-factor verification**:

1. Confirmation from the current owner's registered email address.
2. A secondary verification step (phone verification or security question) initiated by the Account Management team.

Support agents should not process ownership transfers directly. All ownership transfer requests must be escalated to the Account Management team.

## Admin Limits by Plan

| Plan | Maximum Admins |
|------|---------------|
| Free | 1 (owner only) |
| Pro | 5 |
| Business | Unlimited |
| Enterprise | Unlimited |

If a workspace on the Pro plan already has 5 admins, additional admin promotions require an upgrade to Business or Enterprise.

## Agent Instructions

- Always verify identity before processing any admin role change.
- Never grant admin access based solely on a customer's verbal claim.
- Escalate ownership transfers to the Account Management team.
- Check the customer's plan for admin limits before processing role changes.
- Cite this policy when denying unauthorized admin requests.
