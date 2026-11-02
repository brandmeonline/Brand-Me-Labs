# Product Cube Integration - Action Plan

**Date:** October 26, 2025
**Priority:** IMMEDIATE
**Status:** Ready for Testing

---

## IMMEDIATE ACTIONS (Do Now)

### 1. Push Status Report (1 minute)
```bash
git push origin claude/integrate-product-cube-service-011CUWYES9s7CKS2iHFkKBG8
```
**Status:** ⏳ Pending

### 2. Test Service Startup (5 minutes)

```bash
# Start infrastructure services
docker-compose up -d postgres policy compliance orchestrator identity

# Wait for services to initialize
sleep 20

# Start cube service
docker-compose up cube

# Expected output in logs:
# - "cube_service_starting"
# - "database_pool_created"
# - "http_client_created"
# - "cube_service_initialized"
```

**Success Criteria:**
- ✅ No import errors
- ✅ Service starts on port 8007
- ✅ Health check responds

### 3. Verify Health Check (1 minute)

```bash
# In another terminal
curl http://localhost:8007/health

# Expected response:
# {"status":"ok","service":"cube"}

# Also test:
curl http://localhost:8007/health/live
curl http://localhost:8007/health/ready
curl http://localhost:8007/metrics
```

---

## SHORT-TERM ACTIONS (Next Session - 30 minutes)

### 4. Test Policy Integration (15 minutes)

```bash
# Start all services
docker-compose up -d

# Test face access
curl -X POST http://localhost:8001/policy/canViewFace \
  -H "Content-Type: application/json" \
  -d '{
    "viewer_id": "user123",
    "owner_id": "owner456",
    "cube_id": "cube789",
    "face_name": "product_details"
  }'

# Expected: {"decision": "allow", "resolved_scope": "public"}

# Test ownership transfer policy
curl -X POST http://localhost:8001/policy/canTransferOwnership \
  -H "Content-Type: application/json" \
  -d '{
    "from_owner_id": "user123",
    "to_owner_id": "user456",
    "cube_id": "cube789",
    "price": 1500
  }'

# Expected: {"decision": "allow", "reason": "standard_transfer"}
```

### 5. Test Orchestrator API (10 minutes)

```bash
# Test ownership transfer
curl -X POST http://localhost:8002/execute/transfer_ownership \
  -H "Content-Type: application/json" \
  -d '{
    "cube_id": "cube789",
    "from_owner_id": "user123",
    "to_owner_id": "user456",
    "transfer_method": "purchase",
    "price": 1500
  }'

# Expected: Transaction hash and ownership face data
```

### 6. Verify Database Schema (5 minutes)

```bash
# Connect to database
docker-compose exec postgres psql -U brandme -d brandme

# Check tables
\dt cubes
\dt cube_face_access_log

# Check structure
\d cubes

# Verify indexes
\di idx_cubes_*

# Exit
\q
```

---

## MEDIUM-TERM ACTIONS (Next Week - 4 hours)

### 7. Implement Cube Creation Endpoint (2 hours)

**File:** `brandme-cube/src/api/cubes.py`

Add:
```python
@router.post("/")
async def create_cube(
    request_body: CreateCubeRequest,
    request: Request
):
    """Create new Product Cube"""
    # Implementation
```

**Tasks:**
- [ ] Validate product_details
- [ ] Set initial visibility settings
- [ ] Insert into database
- [ ] Return cube_id
- [ ] Log to compliance

### 8. Implement Cube Search Endpoint (1 hour)

**File:** `brandme-cube/src/api/cubes.py`

Complete:
```python
@router.get("/search")
async def search_cubes(
    brand: str = None,
    style: str = None,
    min_sustainability_score: float = None,
    limit: int = 20,
    offset: int = 0,
    request: Request = None
):
    """Search cubes with filtering"""
    # Implementation
```

**Tasks:**
- [ ] Build JSONB query
- [ ] Add pagination
- [ ] Filter by policy
- [ ] Return results

### 9. Write Integration Tests (1 hour)

**File:** `brandme-cube/tests/test_integration.py`

```python
@pytest.mark.asyncio
async def test_full_workflow():
    """Test: Create → Retrieve → Transfer"""
    # Implementation
```

**Tests:**
- [ ] Create cube
- [ ] Retrieve with policy check
- [ ] Transfer ownership
- [ ] Verify escalation

---

## LONG-TERM ACTIONS (Next Sprint - 2 weeks)

### 10. Real Blockchain Integration

**Components:**
- Cardano transaction builder
- Midnight privacy layer
- Transaction verification
- Webhook for confirmations

**Estimated:** 3-5 days

### 11. Redis Caching Layer

**Features:**
- Cache frequently accessed cubes
- Invalidation on updates
- TTL management
- Cache warming

**Estimated:** 2 days

### 12. Comprehensive Test Suite

**Coverage:**
- Unit tests (80%+ coverage)
- Integration tests
- Load tests (100 req/s)
- Security tests

**Estimated:** 3 days

### 13. Monitoring & Alerting

**Setup:**
- Grafana dashboards
- Prometheus alerts
- Log aggregation
- Distributed tracing

**Estimated:** 2 days

---

## VALIDATION CHECKLIST

### Before Merging PR

- [ ] Service starts successfully
- [ ] Health checks pass
- [ ] Policy integration works
- [ ] Orchestrator integration works
- [ ] Database operations succeed
- [ ] All tests pass
- [ ] Documentation reviewed
- [ ] Code review complete
- [ ] Security review (basic)

### Before Production Deployment

- [ ] Integration tests pass
- [ ] Load tests pass (100+ req/s)
- [ ] Security audit complete
- [ ] Monitoring configured
- [ ] Alerts configured
- [ ] Runbook created
- [ ] Rollback plan documented
- [ ] Stakeholder approval

---

## RISK MITIGATION

### If Service Won't Start

**Check:**
1. Import errors → Review logs
2. Database connection → Check DATABASE_URL
3. Port conflicts → `lsof -i :8007`
4. Dependencies → Check other services running

**Actions:**
- Review docker logs: `docker logs brandme-cube`
- Check environment variables
- Verify dependencies started
- Consult CUBE_STATUS_REPORT.md

### If Tests Fail

**Check:**
1. Database schema → Run init.sql
2. Service dependencies → Start all services
3. Environment variables → Check .env
4. Network connectivity → Check docker network

**Actions:**
- Run tests in isolation
- Check test data setup
- Review test logs
- Update test fixtures

### If Integration Issues

**Check:**
1. Policy endpoint → Test directly
2. Compliance service → Check logs
3. Orchestrator → Verify HTTP API
4. Request IDs → Verify propagation

**Actions:**
- Test each service independently
- Check service-to-service connectivity
- Review request/response logs
- Verify timeout settings

---

## SUCCESS METRICS

### Development Complete
- [x] Code written (1,213 LOC)
- [x] Syntax validated
- [x] Imports fixed
- [ ] Service tested
- [ ] Integration tested

### Infrastructure Ready
- [x] Docker config
- [x] Kubernetes config
- [x] Database schema
- [ ] Deployed to dev
- [ ] Deployed to staging

### Documentation Complete
- [x] Integration guide
- [x] Quick start
- [x] API docs
- [x] Status report
- [x] Action plan

### Quality Assured
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Load tests pass
- [ ] Security scan clean
- [ ] Code review approved

---

## TIMELINE

### Week 1 (This Week)
- [x] Day 1-2: Code complete
- [x] Day 2-3: Documentation
- [x] Day 3: Fix import issues
- [ ] Day 4: Test startup
- [ ] Day 5: Integration testing

### Week 2 (Next Week)
- [ ] Day 1-2: Implement missing endpoints
- [ ] Day 3: Write tests
- [ ] Day 4: Code review
- [ ] Day 5: Merge PR

### Week 3-4 (Next Sprint)
- [ ] Week 3: Blockchain integration
- [ ] Week 4: Monitoring & production prep

---

## CONTACT / ESCALATION

### Questions About
- **Code:** Review CUBE_SERVICE_INTEGRATION.md
- **Setup:** Review PRODUCT_CUBE_QUICKSTART.md
- **Status:** Review CUBE_STATUS_REPORT.md
- **Issues:** Check troubleshooting sections

### Next Steps Unclear?
1. Review this action plan
2. Check status report
3. Review git commit messages
4. Consult integration guide

---

## CURRENT STATE SUMMARY

**What's Done:**
- ✅ 1,213 lines of service code
- ✅ 2 policy endpoints
- ✅ 1 orchestrator API
- ✅ Database schema
- ✅ Docker & Kubernetes configs
- ✅ 900+ lines of documentation
- ✅ Import errors fixed

**What's Next:**
1. Test service startup (NOW)
2. Verify health checks (NOW)
3. Test integrations (NEXT SESSION)
4. Implement missing endpoints (NEXT WEEK)

**Blockers:**
- None (code is valid and ready for testing)

**Risks:**
- Untested startup (mitigated: syntax validated)
- Untested integration (mitigated: endpoints implemented)
- Missing endpoints (documented: not blocking)

---

## RECOMMENDED NEXT ACTION

```bash
# Execute now:
docker-compose up cube

# Then in another terminal:
curl http://localhost:8007/health
```

**Expected:** Service starts, health check returns OK

**If successful:** Continue with integration testing

**If issues:** Review logs and troubleshooting guide

---

**Action Plan Created:** October 26, 2025
**Status:** Ready for Execution
**Confidence:** HIGH
