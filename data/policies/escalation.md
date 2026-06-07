# Helios Escalation Rules

**Effective Date:** January 1, 2024
**Last Updated:** April 1, 2025
**Policy ID:** POL-ESCALATION-001

## Purpose

This document defines the mandatory escalation rules for the Helios support team. Certain customer interactions require immediate escalation to specialized teams. Failure to escalate when required is a critical compliance violation.

## Mandatory Escalation Triggers

### 1. Legal Threats

Any message containing a legal threat, mention of litigation, references to attorneys or lawyers, or threats of regulatory complaints must be escalated **immediately** to the Legal team. The agent must not negotiate, offer concessions, or provide legal guidance. The correct response is to acknowledge the customer's concern, inform them that the matter is being escalated to the appropriate team, and provide a reference number.

**Examples:** "I will sue," "my lawyer will contact you," "I'm filing a complaint with the FTC," "this violates consumer protection law."

### 2. Security Incidents

Any report of a security breach, unauthorized access, suspected data exposure, or vulnerability disclosure must be escalated **immediately** to the Security team. The agent should gather basic incident details (what happened, when, which accounts affected) without requesting sensitive credentials or attempting to diagnose the issue.

**Examples:** "Someone accessed my account without permission," "I found a security vulnerability," "our data may have been exposed."

### 3. Executive Complaints

Complaints from or about C-level executives, board members, or high-profile customers must be escalated to the **Customer Success** team. This includes situations where the customer identifies themselves as a senior executive or where the complaint references decisions made at the executive level.

**Examples:** "I'm the CEO and this is unacceptable," "put me through to your management," "I need to speak with someone in charge."

### 4. Repeated Complaints

When a customer has filed **3 or more support tickets** about the same issue and the issue remains unresolved, the case must be escalated to the **Engineering** team for root-cause investigation. The agent should compile a summary of the previous tickets and the common issue before escalating.

### 5. Account Takeover Attempts

Any request that appears to be an attempt to gain unauthorized access to another user's account must be escalated to the **Security** team. This includes requests to change account ownership without proper verification, requests for another user's login credentials, or social engineering attempts.

## Escalation Procedure

When escalating, the agent must:

1. **Acknowledge** the customer's concern clearly and professionally.
2. **Inform** the customer that the matter is being escalated to the appropriate specialist team.
3. **Create** an escalation record using the `create_escalation` tool with the correct team designation.
4. **Provide** the customer with a reference number for tracking.
5. **Set expectations** for response time (typically 1-2 business days for non-urgent, 4 hours for security incidents).

## Agent Instructions

- Never ignore an escalation trigger, even if the customer's tone is polite.
- Do not attempt to resolve legal, security, or account takeover issues independently.
- Always use the `create_escalation` tool to create a formal escalation record.
- Cite this policy when explaining the escalation to the customer.
- A buried or indirect legal threat still requires escalation.
