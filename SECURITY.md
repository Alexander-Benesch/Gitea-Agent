# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | Yes       |
| 1.x     | No (archived) |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** create a public GitHub/Gitea issue
2. Send details to the repository owner via private message
3. Include: description, steps to reproduce, potential impact
4. Expected response time: 48 hours

## Security Measures

S.A.M.U.E.L. implements multiple security layers:

- **14 PR Gates** — automated checks before any code merge
- **PromptGuard Middleware** — enforces invariant markers in LLM prompts
- **Secret Scanner** — blocks .env, credentials, API keys in diffs
- **PII Scrubber** — removes personal data before LLM calls
- **HMAC Integrity** — webhook payload and context slice verification
- **Audit Trail** — full event log with OWASP classification and correlation IDs
- **Circuit Breaker** — prevents cascade failures from provider outages
