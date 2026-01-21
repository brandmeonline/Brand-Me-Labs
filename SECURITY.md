# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x.x   | :white_check_mark: |
| 2.x.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please follow these steps:

### DO NOT

- Open a public GitHub issue
- Post details on social media or forums
- Exploit the vulnerability

### DO

1. **Email**: Send details to security@brandme.io
2. **Include**:
   - Type of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 5 business days
- **Resolution Timeline**: Depends on severity
  - Critical: 24-72 hours
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next release cycle

### Scope

This policy applies to:

- All Brand.Me production services
- Infrastructure configurations
- Client libraries and SDKs
- Mobile applications
- Blockchain smart contracts

### Out of Scope

- Third-party services
- Social engineering attacks
- Physical security
- Denial of service attacks

### Recognition

We maintain a security hall of fame for responsible disclosures. Contributors who report valid vulnerabilities will be acknowledged (with their permission).

## Security Best Practices

### For Contributors

1. **Never commit secrets or credentials** - Use environment variables
2. **Enable 2FA** on your GitHub account
3. **Review dependencies** before adding them
4. **Report suspicious activity** immediately
5. **Follow secure coding guidelines**

### For Deployment

1. **Use TLS** for all communications
2. **Rotate credentials** regularly (90 days max)
3. **Enable audit logging** on all services
4. **Implement rate limiting** on public endpoints
5. **Use least-privilege access** for service accounts

### Sensitive Data Handling

Brand.Me handles several categories of sensitive data:

| Data Type | Protection Level | Storage |
|-----------|------------------|---------|
| User PII | High | Spanner (encrypted) |
| Wallet Keys | Critical | Kubernetes Secrets |
| Blockchain Proofs | High | Midnight (shielded) |
| Session Tokens | High | Redis (encrypted) |
| Consent Records | High | Spanner (audited) |

### Blockchain Security

- **Cardano**: Public chain, ESG proofs only
- **Midnight**: Private chain, ownership/consent data
- **Cross-chain**: Merkle proofs for verification

All blockchain interactions are logged and auditable.

## Vulnerability Disclosure Timeline

1. **Day 0**: Vulnerability reported
2. **Day 2**: Acknowledgment sent
3. **Day 5**: Initial assessment complete
4. **Day 7-30**: Fix developed and tested
5. **Day 30-45**: Coordinated disclosure (if applicable)
6. **Day 45+**: Public disclosure

## Contact

- **Security Team**: security@brandme.io
- **PGP Key**: Available upon request
- **Response Hours**: Monday-Friday, 9 AM - 6 PM EST

## Updates

This security policy was last updated on 2026-01-21.
