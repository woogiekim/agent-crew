# Skill: security-hardening

## Purpose
Enables the backend and devops agents to apply authentication, authorization, secrets management, and transport security patterns correctly — preventing the most common application security failures without requiring a security specialist.

## When to Apply
- When designing authentication or authorization for a new API
- When adding or modifying how credentials and secrets are stored
- When configuring CORS, HTTPS, or security headers
- When setting up CI/CD pipelines that handle secrets

---

## Authentication — JWT Design

(Reference: RFC 7519 — JSON Web Token; OWASP JWT Security Cheat Sheet)

### Token structure

```
Header.Payload.Signature
eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyIsImV4cCI6MTcxNTg2NTYwMH0.sig
```

### Mandatory claims

| Claim | Meaning | Required value |
|---|---|---|
| `sub` | Subject — who the token is about | User ID (opaque string) |
| `exp` | Expiry time (Unix seconds) | Now + token lifetime |
| `iat` | Issued at (Unix seconds) | Now |
| `jti` | JWT ID — unique token identifier | UUID (enables revocation) |
| `iss` | Issuer | Service name / URL |

### Signing algorithm

| Algorithm | Type | Use when |
|---|---|---|
| `RS256` | Asymmetric (RSA 2048+) | Multiple services; public key distribution |
| `ES256` | Asymmetric (ECDSA P-256) | Smaller key size; same security as RS256 |
| `HS256` | Symmetric (HMAC) | Single service only; secret must never leave server |

**Never use `alg: none`**. Reject any token that presents `alg: none` or an unexpected algorithm.

### Token lifetime

| Token type | Lifetime | Storage |
|---|---|---|
| Access token | 15 min – 1 hour | In-memory (JS); HttpOnly cookie (web) |
| Refresh token | 7–30 days | HttpOnly, Secure, SameSite=Strict cookie |

Store access tokens in memory (not `localStorage`) — XSS cannot read memory but can read `localStorage`.

### Spring Boot JWT validation

```kotlin
@Component
class JwtAuthenticationFilter(private val jwtService: JwtService) : OncePerRequestFilter() {
    override fun doFilterInternal(req: HttpServletRequest, res: HttpServletResponse, chain: FilterChain) {
        val token = req.getHeader("Authorization")
            ?.removePrefix("Bearer ")
            ?: return chain.doFilter(req, res)

        try {
            val claims = jwtService.validate(token)  // throws on invalid/expired
            SecurityContextHolder.getContext().authentication =
                UsernamePasswordAuthenticationToken(claims.subject, null, emptyList())
        } catch (e: JwtException) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Invalid token")
            return
        }
        chain.doFilter(req, res)
    }
}
```

---

## OAuth2 / OIDC Flows

(Reference: RFC 6749 — OAuth 2.0; OpenID Connect Core 1.0)

| Flow | Use when | Notes |
|---|---|---|
| **Authorization Code + PKCE** | Web/mobile apps with user login | Current best practice for public clients |
| **Client Credentials** | Machine-to-machine (no user) | Service APIs calling other services |
| **Device Code** | CLI tools, smart TVs | No browser redirect required |
| ~~Implicit~~ | Deprecated | Do not use; replaced by Auth Code + PKCE |
| ~~Password~~ | Deprecated | Only for legacy migration; never for new code |

### Authorization Code + PKCE flow

```
1. Client generates: code_verifier (random 43-128 chars) + code_challenge = SHA256(verifier)
2. Redirect user → /authorize?response_type=code&code_challenge=...&code_challenge_method=S256
3. User authenticates; auth server redirects back with code
4. Client POST /token with { code, code_verifier } → receives access_token + refresh_token
5. Client uses access_token in Authorization: Bearer header
```

---

## Authorization — Role-Based Access Control

```kotlin
// Method-level security (Spring Security)
@PreAuthorize("hasRole('ADMIN') or @orderSecurity.isOwner(#orderId, authentication)")
fun cancelOrder(orderId: OrderId): Either<OrderError, Order> = TODO()

// Custom permission evaluator — prevent IDOR (Insecure Direct Object Reference)
@Component("orderSecurity")
class OrderSecurityEvaluator(private val orderRepository: OrderRepository) {
    fun isOwner(orderId: OrderId, auth: Authentication): Boolean {
        val userId = auth.principal as String
        return orderRepository.findById(orderId)
            .map { it.customerId.value.toString() == userId }
            .getOrElse { false }
    }
}
```

**IDOR prevention rule:** never trust client-supplied IDs for ownership checks. Always verify against the authenticated user's identity server-side.

---

## Secrets Management

(Reference: OWASP Secrets Management Cheat Sheet; HashiCorp Vault docs)

### Never do this
```kotlin
// BAD — secrets in source code
val apiKey = "sk-live-abc123..."
val dbPassword = "supersecret"
```

```yaml
# BAD — secrets in application.yaml committed to git
datasource:
  password: "supersecret"
```

### Environment variable pattern (12-Factor, Factor III)

```bash
# Runtime environment (CI/CD, container, OS)
export DB_PASSWORD="$(vault kv get -field=password secret/db)"
export JWT_SECRET="$(vault kv get -field=key secret/jwt)"
```

```kotlin
// Application reads from env — never from source
@Value("\${DB_PASSWORD}")  // Spring
val dbPassword: String = ""
```

### GitHub Actions secret injection

```yaml
# .github/workflows/deploy.yaml
env:
  DB_PASSWORD: ${{ secrets.DB_PASSWORD }}   # Set in repo Settings → Secrets
  JWT_SECRET: ${{ secrets.JWT_SECRET }}
```

### Secret rotation checklist

- [ ] Secrets have a TTL; rotation is automated
- [ ] Old secret remains valid for a grace period during rotation
- [ ] No secret appears in logs (even partially masked)
- [ ] Git history is clean — scan with `git log -S "secret_value"` or `trufflehog`

---

## CORS — Cross-Origin Resource Sharing

(Reference: Fetch Living Standard — CORS; OWASP CORS Cheat Sheet)

```kotlin
// Spring — explicit allowlist (never use allowedOrigins("*") with credentials)
@Configuration
class CorsConfig : WebMvcConfigurer {
    override fun addCorsMappings(registry: CorsRegistry) {
        registry.addMapping("/api/**")
            .allowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
            )
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .allowedHeaders("Authorization", "Content-Type")
            .allowCredentials(true)           // true requires explicit origins (not *)
            .maxAge(3600)                     // preflight cache seconds
    }
}
```

**Rules:**
- Never combine `allowCredentials(true)` with `allowedOrigins("*")` — browsers block it, and it indicates a security misconfiguration
- Always specify the method allowlist; don't use `allowedMethods("*")`

---

## Security Headers

(Reference: OWASP Secure Headers Project; MDN Web Docs)

```kotlin
// Spring Security HTTP security headers
http.headers { headers ->
    headers.contentSecurityPolicy { csp ->
        csp.policyDirectives(
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self' data:; " +
            "connect-src 'self' https://api.example.com; " +
            "frame-ancestors 'none'"
        )
    }
    headers.frameOptions { it.deny() }
    headers.httpStrictTransportSecurity { hsts ->
        hsts.includeSubDomains(true)
        hsts.maxAgeInSeconds(31536000)  // 1 year
    }
    headers.referrerPolicy { it.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.STRICT_ORIGIN) }
}
```

| Header | Purpose |
|---|---|
| `Strict-Transport-Security` | Force HTTPS for all future requests |
| `Content-Security-Policy` | Prevent XSS by allowlisting script/style sources |
| `X-Frame-Options: DENY` | Prevent clickjacking |
| `X-Content-Type-Options: nosniff` | Prevent MIME type sniffing |
| `Referrer-Policy` | Control what's sent in the `Referer` header |

---

## Input Validation

```kotlin
// Validate at the API boundary — never trust client input
data class CreateOrderRequest(
    @field:NotNull val customerId: UUID,
    @field:NotEmpty @field:Size(min=1, max=100) val items: List<@Valid OrderItemRequest>
)

data class OrderItemRequest(
    @field:NotNull val productId: UUID,
    @field:Min(1) @field:Max(1000) val quantity: Int
)

// In controller
@PostMapping("/orders")
fun createOrder(@Valid @RequestBody request: CreateOrderRequest): ResponseEntity<OrderResponse>
```

**SQL Injection prevention:** always use parameterized queries / prepared statements. Never build SQL via string concatenation.

```kotlin
// GOOD — parameterized
val orders = em.createQuery("SELECT o FROM Order o WHERE o.customerId = :id")
    .setParameter("id", customerId)
    .resultList

// BAD — SQL injection
val orders = em.createQuery("SELECT o FROM Order o WHERE o.customerId = '$customerId'")
```

---

## Checklist
- [ ] JWT uses RS256 or ES256 (not HS256 for multi-service); `exp`, `iat`, `jti`, `sub` claims present
- [ ] Access tokens stored in memory (not localStorage); refresh tokens in HttpOnly cookies
- [ ] OAuth2 flow: Authorization Code + PKCE for user-facing apps; Client Credentials for M2M
- [ ] Authorization: IDOR prevented by server-side ownership check (not trusting client-supplied IDs)
- [ ] Secrets in environment variables only; not in source code or committed config files
- [ ] Git history scanned for committed secrets (trufflehog or gitleaks)
- [ ] CORS: explicit allowlist; never `allowedOrigins("*")` with `allowCredentials(true)`
- [ ] Security headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options set
- [ ] All API endpoints validate input with `@Valid`; parameterized queries used everywhere
- [ ] OWASP Top 10 items checked for all new endpoints (cross-reference code-review.md)
