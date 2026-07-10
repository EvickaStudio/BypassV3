# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch.

Older commits, forks, local modifications, and third-party distributions are not
supported.

## Project scope

BypassV3 is intended for:

* testing reCAPTCHA v3 or reCAPTCHA Enterprise integrations that you own,
  operate, or are explicitly authorized to test;
* controlled integration, end-to-end, and regression testing;
* research using local fixtures or public demo environments intended for
  testing;
* defensive evaluation of server-side verification and anti-abuse controls.

The project is not intended for testing unrelated third-party websites,
circumventing access controls, creating abusive traffic, automating account
creation, spam, fraud, scraping against a site's rules, or any other
unauthorized activity.

Using this repository does not grant permission to test any system.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting or by opening a draft Security Advisory for this repository.

Do not publish a public issue containing exploit details before the report has
been reviewed.

A useful report should include:

* the affected commit or version;
* a clear description of the issue and its impact;
* minimal reproduction steps using a local environment, test fixture, or
  authorized demo target;
* relevant logs with secrets and personal data removed;
* a suggested remediation, when available.

I aim to acknowledge complete reports within seven days. This is a
best-effort open-source project and does not provide a guaranteed response or
remediation SLA.

## Examples of in-scope security issues

Examples include:

* arbitrary code execution;
* unsafe parsing of HAR, protobuf, JSON, or other input files;
* path traversal or unintended file access;
* accidental disclosure of credentials, cookies, tokens, or captured browser
  data;
* unexpected outbound requests caused by insufficient input validation;
* dependency vulnerabilities with a demonstrated impact on this project;
* a validation error that causes the library to contact an unintended host.

## Out of scope

The following are normally out of scope:

* changes in Google's undocumented endpoints, token format, scoring, or risk
  model;
* score differences between networks, devices, actions, or test runs;
* reports that only demonstrate use against an unrelated third-party website;
* requests to adapt the project to a specific third-party service;
* denial-of-service testing, credential attacks, spam, fraud, or account
  automation;
* vulnerabilities in Google reCAPTCHA, 2captcha, GitHub, or another external
  service. Report those issues directly to the affected provider;
* findings that require collecting or sharing another person's browser
  fingerprint, cookies, tokens, or private traffic.

## Sensitive data

Do not include any of the following in a report or commit:

* reCAPTCHA secret keys or other server-side credentials;
* authentication cookies, session identifiers, or bearer tokens;
* production HAR files;
* raw request captures containing personal or device-specific data;
* `fingerprint.json` files captured from a real browser;
* private source code or configuration from a third party;
* personal data that is not necessary to understand the issue.

Redact sensitive values and use synthetic or local fixtures whenever possible.

## Coordinated disclosure

Please allow reasonable time to investigate and publish a fix before disclosing
an unresolved vulnerability publicly.

After remediation, the reporter may be credited in the advisory unless they
prefer to remain anonymous.

## Abuse reports

Reports of repository misuse should identify the relevant public repository,
issue, pull request, or discussion. Do not send captured traffic, credentials,
fingerprints, or private data belonging to another person.

Support may be refused and discussions may be removed when they concern
unauthorized targets or abusive use.

## No security bounty

This project does not currently operate a paid vulnerability disclosure or bug
bounty program.
