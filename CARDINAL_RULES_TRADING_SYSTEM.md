# Cardinal Rules for AI-Powered Trading System

## Document Purpose
This document establishes the fundamental, non-negotiable principles that govern the AI-powered trading system. These rules must be followed by all components, services, and future developments.

---

## Core Trading Rules

### Rule 1: Exchange Reconciliation is Supreme
**The exchange's state is the single source of truth**
- Local registry must reconcile with exchange every 5-10 seconds
- Any discrepancy between local and exchange state triggers immediate reconciliation
- Never execute trades based solely on local state without verification

### Rule 2: Position Zone Transitions are Atomic
**Zone changes must be complete and logged**
- A position can only be in ONE zone at any given time
- Every zone transition must be logged with timestamp and trigger reason
- Zone transition logic must complete or rollback entirely (no partial transitions)

### Rule 3: Risk Limits are Absolute
**Never breach risk parameters**
- Stop loss zones trigger immediate closure - no exceptions
- Maximum position size limits cannot be overridden programmatically
- Portfolio-level risk limits supersede individual position decisions

---

## Position Management Cardinal Rules

### Rule 4: Averaging Steps Follow Fibonacci UPNL Percentages
**Averaging triggers at specific UPNL percentage thresholds**
- Uses REVERSED Fibonacci sequence [21, 13, 8, 5, 3] for distribution
- Thresholds are UPNL percentages relative to margin:
  - Step 1: UPNL% ≤ -42% (add 1x original size)
  - Step 2: UPNL% ≤ -68% (add 2x original size)
  - Step 3: UPNL% ≤ -84% (add 3x original size)
  - Step 4: UPNL% ≤ -94% (add 5x original size)
  - Step 5: UPNL% ≤ -100% (add 8x original size)
- UPNL% = UPNL / Margin where Margin = Position Value / Leverage
- Each averaging step records: order ID, price, quantity, timestamp, UPNL at entry
- Weighted average price must be recalculated after each averaging
- Averaging history survives position closure for analysis

### Rule 5: Surplus Dump Logic is Hierarchical
**Surplus dumping follows strict percentage rules**
- First dump: 50% of surplus at 85% of peak UPNL
- Second dump: Remaining surplus at 50% of peak (size-adjusted)
- After full dump: Reset averaging counter and peak tracking
- Partial dumps do not reset counters

### Rule 6: Manual vs Automated Distinction
**Manual and automated positions are tagged permanently**
- `is_manual` flag is immutable once set
- Manual positions follow same risk rules unless explicitly overridden
- Override reasons must be logged and justified

---

## Data Integrity Rules

### Rule 7: Historical Data is Immutable
**Once written, historical data cannot be modified**
- Closed positions move to append-only historical storage
- Position events are write-once, read-many
- Corrections create new records with references, never modify existing

### Rule 8: Real-time Data Has Priority Lanes
**Critical data paths have guaranteed latency**
- Position updates: <1ms latency requirement
- Market data: <100ms end-to-end processing
- Signal generation: <500ms from trigger to decision
- Performance degradation triggers circuit breakers

---

## System Architecture Rules

### Rule 9: Services are Stateless and Idempotent
**Every service can fail and recover without data loss**
- No critical state stored only in memory
- All operations must be idempotent (safe to retry)
- Service restarts cannot cause position loss or duplication

### Rule 10: Monitoring is Not Optional
**Every action produces observable metrics**
- All trading decisions must be logged with reasoning
- System health metrics collected every second
- Alerting thresholds trigger automatic responses
- No "silent failures" - everything either succeeds or raises alerts

---

## Zone-Specific Cardinal Rules

### Rule 11: Zone Thresholds Follow Hierarchy
**Default → User-Defined → AI-Calculated**
1. System defaults: -0.15$ and +0.15$ for zone boundaries
2. User overrides take precedence over defaults
3. AI calculations can modify only if user enables dynamic adjustment
4. Emergency overrides require manual confirmation

### Rule 12: Zone Actions are Deterministic
**Same conditions always produce same actions**
- Neutral Zone: No automated actions
- Averaging Zone: Size increase at Fibonacci UPNL% thresholds (42%, 68%, 84%, 94%, 100%)
- Surplus Dump Zone: Profit-taking at peak percentages
- Profit Taking Zone: Gradual position reduction
- Stop Loss Zone: Immediate full closure

---

## AI Decision Engine Rules

### Rule 13: Gates Cannot Be Bypassed
**Every signal passes through all validation gates**
1. Signal Integrity Gate - Data validation
2. Market Regime Gate - Context analysis  
3. Portfolio Risk Gate - Risk assessment
4. Execution Gate - Order optimization
- Gates evaluate in sequence
- Rejection at any gate stops processing
- Gate decisions are logged with reasoning

### Rule 14: Model Decisions Require Confidence Thresholds
**No action without minimum confidence**
- Every AI decision includes confidence score
- Actions require confidence above configured threshold
- Low confidence triggers human alert or fallback strategy
- Model performance tracked against actual outcomes

---

## Operational Rules

### Rule 15: Graceful Degradation Over Failure
**Partial functionality is better than complete failure**
- If market scanner fails: Continue managing existing positions
- If AI fails: Fall back to rule-based strategies
- If exchange connection fails: Enter protective mode (close-only)
- If database fails: Switch to emergency cache mode

### Rule 16: Audit Trail is Comprehensive
**Every decision and action is traceable**
- Who (service/user) initiated action
- What action was taken
- When (timestamp with microsecond precision)
- Why (reasoning/trigger)
- Result (success/failure with details)

---

## Performance Rules

### Rule 17: Latency Budgets are Enforced
**Each component has strict latency requirements**
| Component | Maximum Latency | Action on Breach |
|-----------|----------------|------------------|
| Position Registry | 1ms | Circuit breaker activation |
| Market Data | 100ms | Skip data point, alert |
| Signal Generation | 500ms | Timeout, use cached |
| Exchange API | 5000ms | Retry with backoff |

### Rule 18: Resource Limits Prevent Runaway Processes
**Hard limits on resource consumption**
- Memory: No single service exceeds 8GB
- CPU: Process throttling at 80% usage
- Disk: Alert at 70%, stop writes at 90%
- Network: Rate limiting on all external calls

---

## Security Rules

### Rule 19: Secrets Never Touch Code
**API keys and passwords managed separately**
- Secrets stored in dedicated vault (HashiCorp Vault)
- Environment variables for configuration, not secrets
- Automatic secret rotation every 90 days
- Audit log for every secret access

### Rule 20: Defense in Depth
**Multiple security layers protect the system**
- Network: Firewall and VPN requirements
- Application: Input validation and sanitization
- Data: Encryption at rest and in transit
- Access: Multi-factor authentication required

---

## Development Rules

### Rule 21: No Breaking Changes Without Migration Path
**Backward compatibility or migration required**
- API versioning mandatory
- Deprecation notices 30 days minimum
- Migration scripts provided
- Parallel run period for validation

### Rule 22: Testing Mirrors Production
**Test environment matches production exactly**
- Same data structures and volumes
- Same latency requirements
- Same failure scenarios
- Backtesting uses production code paths

---

## Business Logic Rules

### Rule 23: Position Sizing Follows Risk Model
**Never exceed risk-adjusted size limits**
- Dynamic position limit based on available capital and averaging requirements
- Must reserve 20x margin per position (1x original + 19x for Fibonacci averaging)
- Account size limits: Small (<$20): 2 positions, Medium (<$50): 3 positions, Large (>$50): 4 positions
- Minimum 3 averaging steps must be possible or position is rejected
- Leverage: Maximum 10x (currently using 9x)
- Never open positions without full averaging capital reserved

### Rule 24: Market Conditions Override Individual Signals
**Portfolio-level decisions supersede position-level**
- High volatility: Reduce all position sizes
- Low liquidity: Avoid new entries
- System stress: Defensive mode activation
- Black swan detection: Emergency close all

---

## Compliance Rules

### Rule 25: Regulatory Requirements are Non-Negotiable
**All applicable regulations must be followed**
- Transaction reporting as required
- Tax calculation and reporting
- KYC/AML if applicable
- Audit trail preservation (7 years minimum)

---

## Recovery Rules

### Rule 26: Recovery Procedures are Automated
**System self-heals where possible**
- Automatic reconnection to exchange
- Position reconciliation on startup
- Missing data backfill from exchange
- State reconstruction from event log

### Rule 27: Manual Override Requires Confirmation
**Human intervention needs explicit acknowledgment**
- Two-factor authentication for manual trades
- Confirmation of risk acknowledgment
- Logging of override reasoning
- Notification to all stakeholders

---

## Final Cardinal Rule

### Rule 28: When in Doubt, Protect Capital
**Preservation of capital supersedes profit generation**
- Uncertain signals: Don't trade
- System instability: Reduce exposure
- Conflicting indicators: Wait for clarity
- Unknown errors: Safe mode activation

### Rule 29: Dynamic Position & Averaging Management
**Position count and averaging steps must be dynamically calculated**
- Calculate maximum positions based on total capital and averaging requirements
- Every position MUST have full averaging capital reserved (20x margin)
- Recalculate position limits before each scanning cycle
- Existing positions have priority over new positions for capital allocation
- If insufficient capital for minimum 3 averaging steps, reject new positions
- Account for completed averaging steps when calculating reserves

---

## Rule Enforcement

### Violations
- Automatic detection where possible
- Immediate alerting on violation
- Automated response (circuit breakers, position closure)
- Post-mortem required for every violation

### Updates
- Cardinal rules require consensus to change
- Changes must be versioned and documented
- Transition period for rule modifications
- Backward compatibility maintained

---

## Quick Reference Matrix

| Scenario | Cardinal Rule | Action |
|----------|--------------|--------|
| Exchange discrepancy | Rule 1 | Immediate reconciliation |
| Stop loss triggered | Rule 3 | Close position immediately |
| AI confidence low | Rule 14 | Use fallback strategy |
| Latency exceeded | Rule 17 | Circuit breaker activation |
| Unknown error | Rule 28 | Enter safe mode |

---

*Document Version: 1.0*  
*Last Updated: January 2025*  
*Status: Active*  
*Review Cycle: Quarterly*

---

## Usage Notes

1. These rules are incorporated into code as assertions and validations
2. Monitoring systems alert on rule violations
3. Regular audits ensure compliance
4. All team members must acknowledge understanding
5. Changes require architecture review board approval

---

*End of Cardinal Rules Document*