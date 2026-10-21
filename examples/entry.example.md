# Take loyalty points back when an order is refunded

- **Task:** `LOY-214`
- **Project:** loyalty-api
- **Repo:** github.com/acme/loyalty-api
- **Branch:** `feature/LOY-214-refund-points`
- **Stack:** PHP, Laravel, PostgreSQL, Stripe webhooks
- **Layers:** business logic, architecture
- **Risk:** high
- **Logged:** 2026-10-14
- **Review due:** 2026-10-17

## How it works

When Stripe sends charge.refunded, RefundOrderPoints writes a negative refund_reversal row to points_ledger that links back to the order. A balance is never a number I edit: PointsBalance::for() sums the member's ledger rows. A partial refund reverses points in proportion to the refunded amount, rounded down. If the member already spent those points, the reversal stops at their current balance and the rest is stored on the row as unrecovered_points for finance.

## What surprised me

Tiers read lifetime earned points, not the current balance. So a refund lowers my member's balance but never drops them from Gold to Silver.

## What could bite again

Stripe retries webhooks and can send the same refund twice. Only the unique index on points_ledger.source_refund_id stops a second reversal; a check in PHP alone races when two workers pick up the retries together.

## Decisions

### 1. Reverse points with a ledger row, not by editing the balance

*architecture, hard to reverse*

- **Chose:** Insert a negative refund_reversal row in points_ledger, linked to the order and the Stripe refund.
- **Rejected:**
  - UPDATE members.points_balance directly
  - Soft-delete the original earn row
- **Why:** The ledger stays append-only, so support can see why a balance changed and finance can reconcile per order. Soft-deleting the earn row would hide points that were already spent.
- **Impact:** Every balance read is a SUM over the ledger, so the member_id index on points_ledger has to stay.
- **Files:** `app/Points/RefundOrderPoints.php`, `app/Points/PointsBalance.php`

### 2. Stop the reversal at zero instead of allowing a negative balance

*product, reversible*

- **Chose:** Reverse at most the member's current balance and record the shortfall as unrecovered_points.
- **Rejected:**
  - Allow negative balances and block redemptions until they are paid back
  - Hold the refund until the member returns the points
- **Why:** Product's rule is that loyalty points never block a refund, and negative balances confused members in the old app.
- **Impact:** A member who spends points and then refunds keeps that value. Finance sees it in unrecovered_points.
- **Files:** `app/Points/RefundOrderPoints.php`

### 3. Make the refund webhook idempotent with a unique index

*architecture, reversible*

- **Chose:** Add a unique index on points_ledger.source_refund_id and treat a duplicate-key error as already handled.
- **Rejected:**
  - A Redis lock around the webhook handler
  - Check for an existing row in PHP before inserting
- **Why:** The database enforces it across all queue workers. A check-then-insert in PHP lets two retries both pass the check.
- **Files:** `database/migrations/2026_10_14_120000_add_refund_columns_to_points_ledger.php`, `app/Http/Controllers/StripeWebhookController.php`

### 4. Leave tier downgrades on refund for later

*deferred, reversible*

- **Chose:** Tiers keep using lifetime earned points; a refund does not change a member's tier for now.
- **Rejected:**
  - Recalculate the tier on every refund
- **Why:** Downgrading mid-year needs a product rule and a member email that don't exist yet. Tracked as LOY-231.
- **Files:** `app/Tiers/TierCalculator.php`

## Questions

- **I asked:** Make refunds take the points back from the member.
- **I should have asked:** What should happen to points on a partial refund, and when the member has already spent them?
- **How I drove it (3/5):** I pointed straight at StripeWebhookController, which saved time. I didn't mention partial refunds, so the first version took back all 200 points for a $10 refund on a $100 order and had to be redone.

- **I asked:** Is this safe if Stripe sends the same webhook twice?
- **I should have asked:** Show me the test that replays the same refund webhook twice and checks the balance.
- **How I drove it (5/5):** Asking about retries before merging caught a double-reversal bug. Next time I'll ask for the test that proves it, not only the explanation.

## Quiz

**1. Predict.** A member earned 200 points on a $100 order, spent 150 of them, then gets a $50 refund. What happens to their points?

<details><summary>Answer</summary>

Half the order is refunded, so 100 points should go back. Their balance is only 50, so 50 are reversed, 50 are stored as unrecovered_points, and the balance ends at 0.

Proof: `app/Points/RefundOrderPoints.php`

</details>

**2. Why.** Why does a refund add a ledger row instead of lowering points_balance?

<details><summary>Answer</summary>

The ledger is append-only, so every change to a balance has a row that says why and which order caused it. Editing the number would lose that history and break finance reconciliation.

Proof: `app/Points/PointsBalance.php`

</details>

**3. Where.** What stops a retried refund webhook from taking the points back twice?

<details><summary>Answer</summary>

The unique index on points_ledger.source_refund_id. The second insert fails with a duplicate-key error, and the webhook controller treats that as already handled.

Proof: `database/migrations/2026_10_14_120000_add_refund_columns_to_points_ledger.php`

</details>

**4. Trap.** A member refunds the order that got them to Gold. Do they drop back to Silver?

<details><summary>Answer</summary>

No. TierCalculator reads lifetime earned points, which a refund doesn't change. Downgrading on refund is deferred to LOY-231.

Proof: `app/Tiers/TierCalculator.php`

</details>

## Code

`app/Points/RefundOrderPoints.php`

The balance is no longer edited in place; a partial refund reverses a share of the points and never goes below zero.

**Before**

```php
$member->points_balance -= $order->points_earned;
$member->save();
```

**After**

```php
$points = intdiv($order->points_earned * $refund->amount, $order->total);
$reversed = min($points, PointsBalance::for($member));
PointsLedger::create([
    'member_id' => $member->id,
    'entry_type' => 'refund_reversal',
    'points' => -$reversed,
    'unrecovered_points' => $points - $reversed,
    'source_refund_id' => $refund->id,
]);
```
