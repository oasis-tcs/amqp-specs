# AMQP Message Groups Version 1.0

## Working Draft 01

## 24 November 2026

Proposed Standards Track specification. Contributor working draft for AMQP TC discussion; not an approved OASIS Work Product. Extension names await TC allocation.

### This Stage

Local Working Draft 01. No OASIS publication URI has been assigned.

### Previous Stage

N/A. No previous approved publication.

### Latest Stage

No OASIS publication is available.

### Technical Committee

[OASIS Advanced Message Queuing Protocol (AMQP) TC](https://www.oasis-open.org/tc-amqp/)

### Chairs

- Rob Godfrey, IBM.
- Clemens Vasters, Microsoft.

### Author

Eldert Grootenboer, Microsoft.

### Abstract

Applications use message groups to keep related messages with one consumer. AMQP already provides properties for the group and a message's position within it. However, brokers today differ in how they assign groups, end sequences, and recover after an interruption. We want applications to use the same grouping code with any broker that supports the required capabilities. This document proposes ways to get there.

For broker-assigned grouped consumption, we propose using existing AMQP attachment and credit, with the broker assigning groups as it delivers messages. The consumer can receive grouped and ungrouped messages without acquiring or starting each group separately. Optional capabilities let consumers acquire and control individual groups, including cooperative takeover from another consumer, or let the producer declare the end of a bounded sequence with a final message.

A fresh explicit acquisition enables delivery by default. A consumer that needs to know which group it acquired before preparing for delivery requests an initial pause as part of acquisition. When a link using explicit acquisition resumes after an interruption, group delivery remains paused while the consumer checks the broker's list of groups it still owns. The consumer then explicitly enables delivery for each group it is ready to receive.

### Citation Format

**[AMQP-GROUPS]** E. Grootenboer, *AMQP Message Groups Version 1.0*, Working Draft 01, 24 November 2026. Unapproved contribution for AMQP TC discussion.

## License, Document Status, and Notices

Copyright © OASIS Open 2026. All Rights Reserved. See [Annex A](#license-notices) for document status, license, and notices.

<a id="contents"></a>
## Table of Contents

- [1. Scope and required behavior](#scope)
- [2. Support and source settings](#negotiation)
- [3. Broker-assigned grouped consumption](#ordinary)
- [4. Optional explicit acquisition and group controls](#management)
- [5. Lifetime, interruption and recovery](#lifetime)
- [6. Optional producer completion](#sequences)
- [7. Alternatives and implementation precedents](#alternatives)
- [8. Examples](#examples)
- [9. Safety, Security, and Data Protection Considerations](#security-considerations)
- [10. Conformance](#conformance)
- [Annex A. License, Document Status and Notices](#license-notices)
- [Annex B. References](#references)
- [Annex C. Machine-Readable Definitions](#machine-readable-definitions)
- [Appendix 1. Acknowledgments](#acknowledgments)
- [Appendix 2. Changes From Previous Version](#revision-history)

<a id="scope"></a>
## 1. Scope and required behavior

The producer sends messages to a node. The broker stores or routes them and acts as the AMQP sender on the consumer's receiving link. The consumer is the receiver on that link. An application can be a producer in one direction and a consumer in the other.

We propose assigning each group to one consumer per node, such as a queue or subscription. Delivery uses AMQP [`move` distribution](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#section-distribution-nodes). In this mode, a successfully transferred message is no longer available to other links consuming from the same node. Different addresses for the same node share its group assignments. Independent subscriptions have separate group assignments, even when they receive copies of the same publication.

Group assignment determines who receives the next group delivery. It does not transfer application state, stop work at an unreachable consumer or replace application correlation and cancellation. Applications can group work, replies and status messages independently on the nodes receiving them.

Unless marked as existing or core, the group-specific capability symbols, settings, control types and fields, operations, status values, and sequence metadata introduced here are proposed additions. They reuse AMQP 1.0's existing field types and encoding. All error conditions in this proposal are existing AMQP error conditions.

<a id="table-1"></a>
**Table I. Required outcomes.**

| Required outcome | Proposed common behavior |
| --- | --- |
| Related messages stay with one consumer. | Assign the group exclusively before delivery. Settlement, an empty group and zero credit do not silently change its owner. |
| Consumers can receive several groups on one link. | Broker assignment on a shared-capable link is the default. The consumer grants AMQP link credit and receives eligible groups without a separate acquisition command for each group or polling. |
| Consumers can isolate a group on its own link. | Request the proposed [`max-assignments=1` receiving-link setting](#link-settings) to give that group its own link credit and source. |
| Consumers can select a particular group. | Use optional explicit acquisition to acquire a group by its identifier. |
| Consumers can acquire the next available group. | Use optional explicit acquisition to let the broker choose an eligible group. |
| Consumers can request a group held by another consumer. | With optional explicit acquisition, request [cooperative takeover](#cooperative-takeover). The current owner can refuse or safely release the group to the requester, including when the group is empty. |
| Consumers can prepare before group delivery starts. | With optional explicit acquisition, request an initial pause as part of acquisition, then use the proposed [`permit` operation](#management) to enable delivery when ready. |
| Consumers can stop waiting on a quiet group. | Opt into the proposed [consumer receive-idle policy](#idle-switching), then safely relinquish the group before seeking more work. |
| Producers can declare a sequence finished. | Use optional [bounded-sequence support](#sequences). A final indication means the producer has finished sending that sequence, not that the consumer has released the group or finished processing. |
| Interruptions and handover have defined outcomes. | Use core source lifetime and delivery state, with distinct rules for broker-assigned consumption, explicit acquisition, and abandonment. |
| Client code can use different brokers. | Confirm the selected capabilities and parameters. The operations take the same inputs, return the same defined results and errors, and make the same state changes on each broker. |

Capitalized requirement words follow [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119.html) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174.html). They express the requirements of this proposal. [Section 7](#alternatives) compares alternatives and existing implementations. [Section 8](#examples) gives examples of the proposed behavior. Neither section adds protocol requirements. The [AMQP core specifications](#foundations) define encoding, links, credit, delivery state, and transactions.

<a id="negotiation"></a>
## 2. Support and source settings

<a id="capability-selection"></a>
### 2.1 Selecting capabilities

A node implementing this proposal must explicitly advertise grouping support. Adding a group-aware receiver MUST NOT silently change a legacy node's behavior. Receivers that do not participate in the node's grouping contract MUST NOT consume its grouped messages. This includes messages from groups not yet assigned. They may consume eligible ungrouped messages through existing AMQP paths.

Capability negotiation uses AMQP's existing attach fields. The consumer MUST request the proposed base capability `amqp:message-groups-v1` in `attach.desired-capabilities` and verify its confirmation in `attach.offered-capabilities` before granting credit. Optional capabilities likewise require request and confirmation before use. A producer using bounded completion verifies support in the returned target capabilities. The returned capabilities describe the support offered for that link or target. Minimum support and default selection are:

<a id="table-2"></a>
**Table II. Proposed capabilities.**

| Proposed capability | Minimum support and default | Selection and effect |
| --- | --- | --- |
| `amqp:message-groups-v1` | Required for nodes offering this contract. Broker assignment on shared-capable links is the default, with a client-requested one-group limit also supported. | The consumer receives groups through [broker dispatch](#ordinary), subject to its negotiated [receiving-link settings](#link-settings). |
| `amqp:group-management-v1` | Optional and inactive unless requested and confirmed. Offering it requires specific and next-group acquisition, cooperative takeover, and all the operations defined in [section 4](#management). | The consumer selects it in addition to `amqp:message-groups-v1`. Assignments are explicitly acquired by the consumer on that link rather than assigned during dispatch. Both consumers must select it for cooperative takeover. |
| `amqp:group-sequences-v1` | Optional and independent of explicit acquisition. Unbounded grouped messages require no completion metadata. | Producers and consumers using [bounded sequences](#sequences) request and confirm support on their respective links. The application is responsible for receiver compatibility. |

An offered capability not requested by a consumer MUST NOT enable optional behavior on that link. If the broker does not confirm required support, negotiation fails instead of continuing without it. A broker can conform to the required grouping contract without implementing explicit acquisition or bounded completion.

The consumer must be ready for the broker-assigned groups allowed by its negotiated limit. It need not select optional behavior merely because the broker supports it. It MUST NOT silently substitute broker-assigned consumption when the application requires explicit acquisition, group controls, or bounded completion.

<a id="link-settings"></a>
### 2.2 Optional receiving-link settings

We propose an optional entry under symbol `amqp:message-groups-v1` in the existing AMQP `attach.properties` map. Its value uses the proposed `group-settings` type. The `grouped-only` field selects whether the link receives only grouped messages; `max-assignments` limits how many group assignments the link may hold:

<a id="listing-1"></a>
**Listing 1. Group settings type.**

```xml
<type name="group-settings" class="composite" source="list">
  <descriptor name="amqp:group-settings-v1:list"/>
  <field name="grouped-only" type="boolean" default="false"/>
  <field name="max-assignments" type="uint"/>
</type>
```

When settings are absent, `grouped-only=false` and the client imposes no numeric assignment limit, so the consumer accepts multiple eligible groups on the link, subject to node resource limits.

A broker implementing this grouping contract MUST support shared receiving links and the `max-assignments=1` limit. A supplied maximum MUST be positive; the broker returns a positive actual maximum no greater than requested. A confirmed request for one therefore means exactly one. A client requiring shared operation requests a maximum of at least two and MUST verify an actual maximum of at least two before granting credit. If the returned limit does not meet its requirement, it closes the link rather than silently accepting a different arrangement.

Single-group links give each group separate link credit and a separate source to retire. Messages from one group therefore do not consume the link credit allocated to another group's link. Shared links reduce link state and let existing credited links receive work from several groups. One group's deliveries can use up a shared link's credit, blocking deliveries for other groups on that link until the receiver grants more credit. A consumer processing messages one at a time in queue order can also leave one group waiting behind another group's backlog. Single-group links let the application give each group its own receive queue and processing capacity. Links sharing an AMQP session or connection still share those resources. Broker dispatch can use a one-group link, and explicit acquisition can use a shared link. Requiring the one-group limit in the grouping contract gives consumers that isolation choice without requiring optional explicit acquisition.

The broker MUST NOT silently evict held groups to admit new ones. When capacity is exhausted, broker dispatch leaves new groups pending, while explicit acquisition returns the proposed `limit` status defined in [section 4.4](#control-errors).

The broker MUST confirm the requested `grouped-only` value. False permits ungrouped delivery where the node accepts it; true restricts this receiving link to grouped messages. This setting does not change which publications the node accepts. If an ungrouped message is delivered on a confirmed grouped-only link, the consumer MUST send a closing detach with the existing AMQP error condition `amqp:precondition-failed`.

<a id="source-policies"></a>
### 2.3 Source delivery and retention policies

The existing AMQP source describes where a link's messages come from and the delivery settings in use. For a receiving link using this proposed grouping contract, the actual source MUST confirm the existing `move` distribution mode.

Keeping successive messages with the same consumer requires the proposed group assignments, not just `move`. The mode applies to the whole source, so any ungrouped messages sharing that link also use `move`. Existing outcome and recovery rules can still cause redelivery.

Before granting credit or sending group-control requests, the consumer MUST also check its returned settings: the filter, outcomes, default outcome, durability, expiry policy, and timeout. These must meet the consumer's needs.

When omitted, the core defaults remain `durable=none`, `expiry-policy=session-end`, and `timeout=0`. Durability describes which source state survives a broker restart. The expiry policy and timeout determine when the source expires. A consumer that needs retention or recovery after a restart requests suitable source values and checks the returned ones. The broker MUST refuse a requirement it cannot meet rather than silently shorten or weaken it. Group bindings follow the source's actual lifetime. Only these source settings configure how long the broker retains group bindings; the [consumer idle policy](#idle-switching) does not change them. Using one retention policy avoids conflicting durations in source and group-control records.

The broker MUST explicitly return the valid `source.default-outcome` it will use for unresolved deliveries during cleanup. An outcome describes what happened to a delivery, such as acceptance or release for redelivery. The consumer may request, for example, `released()`. It MUST detach before using the source if the returned policy does not meet its requirement. The default is not necessarily Released, and grouping sources need not all offer the same outcomes. Core [`source` fields](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#type-source) specify the available outcomes separately from the default outcome.

Filters use existing AMQP filter-set negotiation. A supported filter condition, or predicate, MAY select or exclude complete groups. It applies consistently to every message of a selected group and remains stable while that group is assigned. A predicate that selects only part of a group, or changes the group's eligibility while assigned, MUST be refused with `amqp:precondition-failed`. A partial filter could leave an earlier nonmatching message queued while later matching messages are delivered. The same group cannot be sent to another owner concurrently, so this could block progress or break the full-group order. Filtering ungrouped messages follows the existing AMQP filter contract. This proposal adds no filter language.

If negotiation fails, the broker returns an attach with a null local terminus, then detaches. The local terminus is the broker's source or target for that link. The error is `amqp:not-implemented` for missing required support, `amqp:invalid-field` for invalid fields, or `amqp:precondition-failed` for requirements or combinations the broker cannot grant.

<a id="ordinary"></a>
## 3. Broker-assigned grouped consumption

### 3.1 Assignment through dispatch

Messages identify their group through the existing string [`properties.group-id`](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#type-properties). Producers intending independent groups MUST choose distinct values within the logical node's scope. Producers deliberately using the same value contribute to the same group.

A consumer relying on broker dispatch attaches, checks the negotiated behavior, and grants credit. If an eligible group has no owner, the broker MUST atomically assign it to the receiving source before starting its first new acquiring delivery. An acquiring delivery reserves the message for that receiving link rather than leaving it available to competing links. Another source MUST NOT concurrently acquire the group's messages. The consumer learns the group from `group-id` on the first message. No group-control command, new assignment annotation, or separate confirmation frame is required.

The source can hold one or several groups. Link credit tells the sender how many new message deliveries it may start. By granting credit, the consumer declares that it is ready for any eligible group. Withholding credit delays the whole link. When no work is available, the consumer waits through the existing receiving path. Before receiving, a consumer can request a supported source filter to restrict broker assignment to whole groups such as `x`, `y`, or `z`. The broker still assigns each group before its first delivery; the filter is not an acquisition request and does not reserve ownership. A matching group already assigned to another consumer stays with that consumer until its assignment ends.

Messages without a group use existing AMQP delivery and create no group assignment. Existing `message-id`, `group-sequence` and `reply-to-group-id` remain optional unless a selected contract specifically requires them. Merely using grouping MUST NOT require producer-completion metadata.

The broker MUST preserve an assignment when deliveries settle, the group is temporarily empty, credit reaches zero, or drain completes. This keeps later messages, including follow-ups after earlier deliveries settle, with the same consumer. The broker MUST NOT silently replace the assignment because another consumer appears, capacity is needed, sequence numbering restarts, or a producer sends a final message. An assignment ends through source destruction, abandonment by closing the link, explicit release, or reported ownership loss, as defined in [section 5](#lifetime).

The [broker-assigned consumption example](#81-broker-assigned-consumption) shows attachment, credit, and delivery of grouped and ungrouped messages.

<a id="delivery-order"></a>
### 3.2 Delivery order

The node MUST establish group order when messages become available for delivery: after a send outside a transaction succeeds at the node, or after the transaction containing the messages commits. If one transaction sends several messages, the node preserves their order within that transaction. The node also orders work from independent concurrent producers or transactions.

The broker MUST start deliveries within a group in that order. The existing AMQP `header.priority` value MUST NOT allow later available work to pass earlier work in the same group. Expiry and rejection can remove messages from the stream without changing the order of the remaining messages. Deliveries from different groups may be interleaved.

Messages made available again by valid outcomes or rollback MUST retain their original positions ahead of later group deliveries that have not yet started. Returning a message does not recall later transfers already sent.

Returned messages remain tied to the group's current assignment. The broker MUST NOT send a returned message to a different receiving source until that assignment has ended and the old message acquisition has been resolved. Repeated returns do not change this. While a group's deliveries are paused by the proposed [`pause` operation](#group-operations), the broker MUST NOT start new deliveries for it, including redeliveries.

Existing AMQP outcome restrictions also apply. When the existing `modified` outcome sets `undeliverable-here=true`, the message cannot be redelivered to that link endpoint. This does not release its group or authorize delivery to a different consumer while the assignment remains held.

These rules order delivery attempts, not application completion. The broker does not sort messages by `group-sequence`, wait for missing positions or suppress duplicates under this contract. Consumers decide how to serialize their work.

> **Considered alternative: sequence-number ordering**
>
> Sorting messages by sequence number could restore their producer-assigned order, but requires a common numbering authority, a policy for missing messages, rules for wraparound and restart, and bounded buffering. We recommend the order in which messages become available at the node because the use cases do not require those additional guarantees.

### 3.3 Replies and status streams

A replying producer can use the existing `properties.reply-to-group-id` as the outgoing `group-id` where its application binding calls for that behavior. The reply address still selects the destination and the binding's correlation value identifies the exchange.

For example, a work queue and a response queue assign their groups separately. The consumer handling a work group is not automatically the consumer assigned to a reply group. The reply consumer chooses broker-assigned consumption or explicit acquisition independently of the work consumer.

<a id="management"></a>
## 4. Optional explicit acquisition and group controls

<a id="group-operations"></a>
### 4.1 Operations and readiness

When the consumer selects the proposed [`amqp:group-management-v1` capability](#capability-selection), it uses explicit acquisition: it asks for a specific group or asks the broker to choose the next eligible group. The link starts with no assignments. The broker MUST NOT assign a group on that link without a successful `acquire` request from the consumer. The consumer decides when to request another group after release. Ungrouped messages remain eligible for AMQP credit-based delivery unless grouped-only reception was selected.

The consumer sends these proposed group-control requests to the broker in a Flow frame whose handle identifies that receiving link. They use the proposed `amqp:group-control-v1` key in the existing `flow.properties` map. Its value is a proposed `group-control` record identifying the operation and request number and, where applicable, the group and current assignment UUID. [Section 4.3](#control-values) defines the record and required fields; [section 8.2](#explicit-acquisition-example) shows the exchanges. The table below describes the preconditions and broker actions for each request.

Core [transactional acquisition](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transactions-v1.0-os.html#doc-idp130640) already uses `flow.properties` to associate subsequent message acquisitions with the transaction identified by its `txn-id` entry.

For example, this illustrative Flow frame requests group `"G"`:

<a id="listing-2"></a>
**Listing 2. Specific-group acquisition Flow.**

```text
consumer -> broker: flow(
  handle=h,
  ...,
  properties={
    symbol("amqp:group-control-v1"):
      described(symbol("amqp:group-control-v1:list"),
        [symbol("request"), ulong(1), symbol("acquire"), "G"])
  })
```

Here, `h` is the receiving link's actual handle, and `...` represents the other Flow fields with valid current values. Flow and its `handle` and `properties` fields are existing AMQP. The map key and described control type are proposed additions.

The list begins with `kind`, `request-number`, `operation`, and `group-id`: this is request 1 to acquire group `"G"`. The broker replies with a `result` record identifying the request and reporting its status. [Section 4.4](#control-errors) defines the proposed statuses and their existing AMQP errors.

An `acquire` request can also include the proposed Boolean field `start-paused` to keep that group's deliveries paused while the consumer prepares to receive them.

To request a group held by another consumer, the requester sets the proposed Boolean `takeover` field to true in a specific-group `acquire` request. The broker asks the current owner to cooperate; this does not force the owner to release the group. [Section 5.2.2](#cooperative-takeover) defines that handover.

The broker identifies the pending handover with a UUID in the proposed `handover-id` field. The owner returns that identifier when refusing or releasing the group for that handover, so a response cannot affect a different request.

<a id="table-3"></a>
**Table III. Group operations.**

| Proposed operation | Preconditions and proposed effect |
| --- | --- |
| `acquire` | Check authorization and capacity, then assign a specific or next eligible group with available work. With `takeover=true`, request cooperative handover of a specific owned group instead; an owner-approved handover can transfer an empty group. Generate a fresh UUID and send success before any new delivery for the new assignment. Enable group delivery unless `start-paused=true` was requested. |
| `permit` | For the held group and UUID, enable new deliveries under AMQP link credit and session windows. Another valid `permit` request with a new `request-number` returns `ok` if delivery is already enabled. |
| `pause` | Stop starting new deliveries for the group, complete or abort its partial transfers, then send the result after those transfers. Ownership remains held; a request for an already paused group also succeeds. |
| `release` | The assignment must already be paused, and the broker must have no incomplete, unsettled, or unresolved transactional deliveries for that group. Without `handover-id`, remove only that assignment and allow another acquisition. With a valid `handover-id`, transfer it directly to the requester. [Section 5.2](#handover) defines the consumer's work-resolution responsibilities. |
| `refuse` | The current owner declines the handover identified by `handover-id`. End the requesting acquisition without changing the owner's assignment or delivery state. |
| `recover` | The consumer sends `recover` before any other group-control request after resuming its retained link. After resolving pending work from the previous attachment, return every retained assignment and UUID, all paused. [Section 5.3](#recovery) defines the resumption flow and when reconciliation is complete. |

Acquiring a group already held by the same source returns `invalid`; the broker does not issue another UUID. A next-group request selects an eligible unassigned group, not another instance of one already held. Once a group is acquired, becoming empty does not end its assignment.

If `start-paused` is omitted or null in an acquire request, it means false. Success MUST explicitly confirm the effective Boolean. The broker MUST honor true rather than downgrade it. With false, the consumer processes the result before dispatching following transfers to handlers. This does not wait for asynchronous application initialization to finish. If the consumer needs the assigned group ID to prepare for processing, such as loading that group's saved state, it sets `start-paused=true` in the `acquire` request and sends `permit` for that assignment after preparation is complete. Withholding credit is sufficient when preparation needs to delay the whole link.

When the broker processes the proposed `pause` request, it stops starting new deliveries for that group, completes or aborts any partly transferred messages, and then sends the successful result. Until that result arrives, the consumer MUST keep receiving and allow enough incoming transfer frames through its session window for those transfers to complete or abort. Otherwise, a blocked transfer can prevent the broker from completing the pause. The result confirms that deliveries for the group have stopped. Pausing does not settle deliveries already received or wait for their application handlers to finish. Sending zero link credit alone does not provide this confirmation because transfers may already be in flight. An existing AMQP Flow echo reports flow state, not the result of the proposed `pause` operation.

<a id="acquisition-wait"></a>
### 4.2 Waiting for acquisition

The consumer can use the proposed `wait` field to control how long the broker waits to acquire a group. This field belongs to the `group-control` record in an `acquire` request. The consumer sends that record under `amqp:group-control-v1` in the receiving link's existing `flow.properties` map, as in [section 4.1](#management).

For example, this control value requests group `"G"` with a wait of at most 30 seconds. The null entries preserve the field positions defined in [section 4.3](#control-values); `seconds(30)` uses the existing AMQP `seconds` type:

<a id="listing-3"></a>
**Listing 3. Acquisition with a finite wait.**

```text
described(symbol("amqp:group-control-v1:list"),
  [symbol("request"), ulong(1), symbol("acquire"), "G",
   null, null, null, null, seconds(30)])
```

An ordinary acquisition requires available messages, a match with the receiving source's filters, and no current owner. It names a specific group or lets the broker choose the next eligible group. Requiring available messages avoids reserving assignment capacity for a new empty group. Cooperative takeover can instead transfer an already assigned group, including an empty one, with its owner's agreement. A group that becomes empty after acquisition remains assigned.

The `wait` value is measured in seconds. If it is null or omitted, the request can keep waiting until a group can be assigned, unless it fails or the attachment ends. With zero, the broker tries to assign a group without waiting for one to become available. If no eligible group is available, it returns an acquisition `result` with the proposed `status=unavailable`. That result ends the request without creating an assignment or leaving a reservation. A positive value lets the broker wait for up to that many seconds after receiving the request, ending the wait when it assigns a group or returns a refusal. Available work can be assigned immediately for any `wait` value.

Each waiting acquisition request, including cooperative takeover, counts as one slot against the actual negotiated `max-assignments` limit from [section 2.2](#link-settings), together with groups already held on that link. An ordinary waiting request does not reserve a group. A pending takeover identifies its requester but leaves ownership with the current owner. On success, the waiting slot becomes the new assignment; it is not counted twice. If no numeric maximum is negotiated, the client imposes no numeric assignment limit. Node resource limits still apply.

Authorization failures, invalid requests, and insufficient assignment or resource capacity cause immediate failure. If a positive wait expires before a group can be assigned, the broker also returns `status=unavailable`. An `unavailable` result carries the existing AMQP error `amqp:resource-locked` if the specifically requested group is still held by another source, otherwise `amqp:not-found`. [Section 4.4](#control-errors) defines these result statuses. The broker MUST NOT commit an assignment for that request after returning refusal.

The broker's waiting period does not include network time delivering the response. Acquisition may already have succeeded when the consumer's own response timeout expires. It may also succeed after that timeout, before the broker observes the end of the attachment. The consumer MUST then treat the outcome as unknown and follow [section 5.4](#interruption). When the attachment is retired, the broker cancels any request still waiting. If the broker has already completed an assignment, and the source and assignment survive the interruption, that assignment is included in the retained assignments returned by `recover`, as described in [section 5.3](#recovery).

The [acquisition example](#explicit-acquisition-example) shows finite and zero waits.

<a id="control-values"></a>
### 4.3 Control values and conditional fields

The consumer and broker use the proposed symbol key [`amqp:group-control-v1`](#group-operations) in the existing [`flow.properties`](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transport-v1.0-os.html#type-flow) map, with the actual attached-link handle. A handle identifies the attached link within its session. AMQP Flow frames carry credit and session-window information. The new entry carries a value of the proposed `group-control` type:

<a id="listing-4"></a>
**Listing 4. Group control type.**

```xml
<type name="group-control" class="composite" source="list">
  <descriptor name="amqp:group-control-v1:list"/>
  <field name="kind" type="symbol" mandatory="true"/>
  <field name="request-number" type="ulong"/>
  <field name="operation" type="symbol"/>
  <field name="group-id" type="string"/>
  <field name="assignment-id" type="uuid"/>
  <field name="status" type="symbol"/>
  <field name="error" type="error"/>
  <field name="assignments" type="list"/>
  <field name="wait" type="seconds"/>
  <field name="start-paused" type="boolean"/>
  <field name="takeover" type="boolean" default="false"/>
  <field name="handover-id" type="uuid"/>
</type>
```

Field positions are fixed; omitted trailing fields are null.

The proposed `group-control` fields distinguish the group, its assignment, and each control request:

<a id="table-4"></a>
**Table IV. Control field lifetimes.**

| Field | Purpose and source | Lifetime |
| --- | --- | --- |
| `group-id` | Identifies the group using the string supplied by the producer in the existing AMQP `properties.group-id` message property. | The same group ID can be used across successive assignments. |
| `assignment-id` | Identifies one assignment of that group. The broker generates a UUID when acquisition succeeds, so controls for an old assignment cannot affect a new one. | Fresh on acquisition; unchanged when that assignment is recovered. |
| `request-number` | A positive `ulong` supplied by the consumer to match a control request with the broker's result. | Scoped to the current attachment; [section 4.4](#control-errors) defines its numbering rules. |
| `takeover` | Selects cooperative takeover in a specific-group `acquire` request. False, null, or omission selects ordinary acquisition. | Applies only to that acquisition request. |
| `handover-id` | Identifies the pending handover notified to the owner. The broker creates it and binds it to the group, old assignment, requesting source, and both attachments. | Valid only while that handover remains pending. It is not an authorization credential. |

The tables and examples below use G as shorthand for `group-id` and A for `assignment-id`.

The proposed `kind` field distinguishes consumer `request` records, broker `result` records, `handover` notifications asking the current owner to cooperate, and `lost` notifications reporting an assignment loss. The `status` field reports a request's result; `error` carries an existing AMQP error value when required. The `assignments` field carries the retained group inventory returned by `recover`.

<a id="table-5"></a>
**Table V. Control record kinds.**

| Proposed kind and direction | Required values | Conditional fields |
| --- | --- | --- |
| `request`, consumer to broker | A positive `request-number` and an `operation` value of `acquire`, `permit`, `pause`, `release`, `refuse`, or `recover`. | `status`, `error`, and `assignments` are absent. `acquire` has no `assignment-id` or `handover-id`; null `group-id` requests the next group. Only `acquire` may use `wait`, `start-paused`, and `takeover`. `takeover=true` requires a non-null `group-id` and a positive `wait`. `recover` has neither group field. `permit`, `pause`, `release`, and `refuse` require `group-id` and `assignment-id`. Only `release` and `refuse` may carry `handover-id`; it is mandatory for `refuse`. |
| Successful acquire `result`, broker to consumer | Echo the request's `request-number` and `operation`, with `group-id=G`, a fresh `assignment-id=A`, `status=ok`, and the effective non-null `start-paused` Boolean. | `error`, `assignments`, `wait`, `takeover`, and `handover-id` are absent. A specifically requested `group-id` MUST match. |
| Successful recover `result` | Echo the request's `request-number` and `operation`, with `status=ok` and the complete retained assignment list in `assignments`, including an empty list when no assignments survived. | Top-level `group-id`, `assignment-id`, `error`, `wait`, `start-paused`, `takeover`, and `handover-id` are absent. |
| Other successful `result` | Echo the request's `request-number`, `operation`, `group-id`, and `assignment-id`, with `status=ok`. A handover-specific `release` or `refuse` also echoes `handover-id`. | `error`, `assignments`, `wait`, `start-paused`, and `takeover` are absent. `handover-id` is absent unless present in the request. |
| Failed `result` | Echo the request's `request-number` and `operation`, with a defined `status` and a core error in `error`. | `assignments`, `wait`, `start-paused`, and `takeover` are absent. `permit`, `pause`, `release`, and `refuse` echo the request's group fields and any supplied `handover-id`. `acquire` may echo the requested `group-id` but MUST NOT disclose an owner's `assignment-id` or `handover-id`. `recover` has neither group field nor `handover-id`. |
| `handover`, broker to current owner | `group-id=G`, the owner's current `assignment-id=A`, and a fresh `handover-id`. | All other fields are absent. This notification is not a result and does not use either consumer's `request-number`. |
| `lost`, broker to consumer | `group-id=G`, the former `assignment-id=A`, and a core error in `error`. | `request-number`, `operation`, `status`, `assignments`, `wait`, `start-paused`, `takeover`, and `handover-id` are absent. This does not answer a pending request. |

Controls MUST preserve valid current Flow sequence and window state and MUST NOT implicitly change credit, drain, or `txn-id`. Group controls consume no transfer-window slots, but share the connection's ordered byte stream. The consumer and broker process controls without waiting for application handlers.

Fields not permitted for a record's kind and operation MUST be absent.

The `assignments` field in a successful result for the proposed [`recover` operation](#recovery) lists the group assignments retained by the broker for that source. Each entry uses the proposed `group-assignment` type:

<a id="listing-5"></a>
**Listing 5. Group assignment type.**

```xml
<type name="group-assignment" class="composite" source="list">
  <descriptor name="amqp:group-assignment-v1:list"/>
  <field name="group-id" type="string" mandatory="true"/>
  <field name="assignment-id" type="uuid" mandatory="true"/>
</type>
```

<a id="control-errors"></a>
### 4.4 Correlation, authorization and errors

Publication requires the node's send rights; consumption and acquisition require its consume rights. An operation on an assigned group MUST check the authenticated principal, logical source, G and A. The principal is the identity authenticated for the consumer. Knowing G or A does not by itself authorize an operation. The broker checks authorization before reporting whether a group is available for acquisition. If the consumer is not authorized, the broker returns `status=denied` without reporting availability.

The `request-number` values MUST increase strictly, without reuse or wrap on an attachment. Each `request-number` is consumed before evaluation, including when a request is refused. Exhaustion requires a new attachment.

On each receiving source, there MUST be at most one unresolved operation per group or [pending acquisition slot](#acquisition-wait). A requesting consumer's pending takeover does not block the owner's own `pause`, `release`, or `refuse` requests. Different groups can proceed independently, and results may arrive out of `request-number` order. The consumer matches `request-number`, `operation`, the applicable group fields, and any `handover-id` echoed from its request.

The broker checks the current owner's authenticated principal, source, group, and assignment before processing a handover response. It MUST also verify that `handover-id` identifies the pending request bound to those attachments. Knowing that identifier does not authorize a transfer. A `handover` notification for a former `assignment-id` cannot affect a later assignment.

The consumer and broker send each group-control record once, without automatically sending it again. After the broker refuses an operation, the consumer may try it again with a new request. If the operation's outcome is unknown, the consumer does not repeat it and follows [section 5.4](#interruption).

If the outcome of `release` is unknown, the broker may already have released the group. The consumer MUST NOT start handlers for messages buffered under that assignment merely because it receives another delivery or assignment.

A control naming the `assignment-id` of an earlier assignment MUST NOT affect a later assignment of the same group. When the consumer receives a `lost` notification, it checks which assignment the notification identifies. A notification naming an earlier assignment cannot invalidate a later assignment, even if its field types are valid.

Failed operations MUST NOT silently change ownership or whether group delivery is enabled. After checking that a result matches the request, the consumer uses its `status` and applicable `assignment-id` to interpret the result, not diagnostic error text.

<a id="table-6"></a>
**Table VI. Control status and error values.**

| Proposed status | Existing AMQP error | Meaning |
| --- | --- | --- |
| `ok` | Absent. | Operation completed successfully. A valid `permit` request also succeeds when delivery is already enabled, and a valid `pause` request also succeeds when delivery is already paused. |
| `unavailable` | `amqp:resource-locked` or `amqp:not-found`. | Ordinary acquisition found no eligible group without waiting or before its deadline. For takeover, the owner refused, cannot participate, or the handover was cancelled or expired. The requesting acquisition ends without a new assignment. A handover-specific release also returns `unavailable` if its requester can no longer receive the group. |
| `busy` | `amqp:precondition-failed`. | A paused `release` has incomplete, unsettled, or unresolved transactional deliveries; ownership stays held and paused. A takeover request also returns `busy` when another handover for that group is already pending, without changing ownership or delivery. |
| `not-ready` | `amqp:precondition-failed`. | `release` was requested while delivery for the group is enabled. The consumer keeps the assignment, and delivery remains enabled. |
| `limit` | `amqp:resource-limit-exceeded`. | The [assignment and waiting-request capacity](#acquisition-wait) or node resources are exhausted, or acquiring another group would exceed the [retained-assignment list size limit](#recovery) for a source that can survive detachment. No assignment is created or evicted. |
| `stale` | `amqp:precondition-failed`. | The supplied group/assignment does not belong to this source, or `handover-id` no longer identifies its pending handover. The current assignment is neither changed nor disclosed. |
| `denied` | `amqp:unauthorized-access`. | The consumer is not authorized to perform the requested `operation`. No operation is performed; the broker does not disclose which consumer owns the group or that assignment's `assignment-id`. |
| `unsupported` | `amqp:not-implemented`. | The `operation` value is not supported. The `group-control` record otherwise has valid structure; no operation is performed. |
| `invalid` | `amqp:invalid-field`. | The `group-control` record has valid structure, but a recognized `operation` has an invalid operation-specific value or field combination. No operation is performed. |
| `state-lost` | `amqp:precondition-failed`. | Required retained source or group-assignment state could not be [recovered](#recovery). |

The statuses above describe results returned for group-control requests. Other failures are reported through existing AMQP frames: `detach` with `closed=true` closes the affected link, `end` ends the session and its links, and `close` closes the connection and its sessions and links. The frame's `error` field carries the error `condition` and may include a diagnostic `description`. The table below defines the required responses under the [record and field rules](#control-values) and request-sequencing rules.

These frames do not carry a group-control `request-number` or confirm each pending operation's outcome. Operations without confirmed results may have unknown outcomes. If the connection fails before the error frame arrives, the consumer may not receive that error. The consumer follows the [unknown-outcome rules](#interruption).

<a id="table-7"></a>
**Table VII. Invalid control input.**

| Invalid input | Required handling |
| --- | --- |
| Undecodable core encoding | If the error is isolated to an identified link, the consumer or broker detecting it sends a closing detach for that link with `amqp:decode-error`. If no trustworthy frame or endpoint can be identified, it closes the connection with that error. It does not invent a `result`. |
| Wrong `group-control` descriptor or type, missing a required record-structure or request/result matching field, unknown `kind` or wrong direction | The consumer or broker receiving the invalid record sends a closing detach for the affected link with `amqp:invalid-field`. |
| Zero, repeated, decreasing, exhausted or reused `request-number`; more than one pending operation per group or pending acquisition slot; operation before required recover | The broker sends a closing detach for the affected link with `amqp:illegal-state`. |
| Valid `group-control` record structure but invalid operation-specific combination | The broker returns an `invalid` result with `amqp:invalid-field`, echoing the request's `request-number` and `operation` and including the group fields required by [section 4.3](#control-values). |
| Valid `group-control` record structure and unknown `operation` | The broker returns an `unsupported` result with `amqp:not-implemented`, echoing the request's `request-number` and `operation` and including the group fields required by [section 4.3](#control-values). Record-structure errors still take precedence. |
| Result has a `request-number` with no pending request, mismatches `operation` or the applicable `group-id` and `assignment-id`, or violates required fields | The consumer sends a closing detach for the affected link with `amqp:invalid-field`. The outcomes of affected operations remain unknown. |
| Unattached Flow handle | The consumer or broker receiving the Flow frame ends the affected session with the existing AMQP session error `amqp:session:unattached-handle`. |

Assignment-loss errors and pending-request handling are defined in [section 5.5](#cleanup).

<a id="lifetime"></a>
## 5. Lifetime, interruption and recovery

### 5.1 Source lifetime

In both broker-assigned consumption and explicit acquisition, the broker retains the group assignments associated with the source of the consumer's receiving link for that [source's confirmed lifetime](#source-policies). Explicit acquisition also requires retaining the `assignment-id` returned by `acquire`, used by subsequent controls, and returned unchanged by `recover`. Group assignments need retained state separate from the core unsettled map: a group can remain assigned after all its deliveries have settled. Brokers serving the same logical node MUST coordinate these assignments.

After a non-closing detach, assignments remain held until the source expires under its confirmed [AMQP expiry policy and timeout](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#type-terminus-expiry-policy). Here, `policy/timeout` abbreviates `source.expiry-policy` and `source.timeout`, with timeout in seconds. For example, `link-detach/0` ends retention on detach, while `session-end/0` retains assignments while the session remains open. A zero timeout means immediate expiry when the selected expiry event occurs; with `expiry-policy=never`, the source does not expire automatically.

Recovery after a broker restart, when requested, requires `source.durable=unsettled-state` and durable group assignments, not just the source's existence and configuration. These settings do not make non-durable messages durable.

Abandoning the source with a closing detach ends its group ownership and invokes [cleanup](#cleanup). Node deletion or loss of assignment state also ends the affected assignments. A broker MUST report failure rather than silently move or reconstruct an assignment it promised to retain.

<a id="handover"></a>
### 5.2 Cooperative ordered handover

A consumer using explicit acquisition hands over a group by pausing delivery, resolving its existing work, and releasing the assignment. It sends `pause` for that group and waits for the successful result. It then resolves any remaining partial-delivery state, finishes handling messages already started or returns unprocessed unsettled messages using supported outcomes, and waits for the required settlement and transaction resolution.

The consumer MUST also resolve its pre-settled buffer and stop starting old buffered work before requesting `release`. Pre-settled messages were already settled by the sender, so they cannot be returned through a new disposition. Once that work is resolved, the consumer sends `release` for the group and its current `assignment-id`.

The broker returns `not-ready` if `release` is requested while delivery is enabled. It returns `busy` if the group is paused but incomplete, unsettled, or unresolved transactional deliveries remain. Receiving a producer's [final indication](#sequence-metadata) does not satisfy either release condition. After successful release, the old consumer MUST NOT start handlers from its earlier buffer. After a failed release, it can resume handling only while its assignment remains valid and delivery is enabled.

A `release` without `handover-id` does not reserve the group for a particular consumer. Any eligible consumer can acquire it with a fresh `assignment-id`, and acquisition may succeed on another connection before the releasing consumer receives its result. Delivery is enabled by default, subject to credit, or the acquiring consumer can request `start-paused=true`. [Cooperative takeover](#cooperative-takeover) uses the same work-resolution procedure but assigns the group directly to the requester.

For a whole-link shutdown, the consumer can use core link flow control to stop delivery on the whole link and confirm that no more transfers will arrive. It then resolves its deliveries and sends a closing detach; this path does not require per-group controls. If deliveries remain unresolved when the source is abandoned, the broker follows [cleanup](#cleanup) rather than treating cooperative handling as complete.

The [plain-release example](#83-ordered-handover-and-busy-release) shows pause, an outstanding settlement that prevents release, and subsequent acquisition by another consumer.

<a id="idle-switching"></a>
#### 5.2.1 Optional consumer idle switching

A consumer may opt into a finite receive-idle wait: how long it waits for another message on a group before ending that assignment and looking for another group. This is a proposed consumer policy, not an attach property or a broker timer. If the policy is not selected, a quiet group remains assigned as before. Making it opt-in preserves continuity for applications expecting later messages on that group; selecting it lets a consumer look for other work, especially on a one-group link.

The wait starts after the consumer has finished the group's buffered and active work and is ready to receive more. The consumer keeps receiving during the wait; deliberate pause or withheld credit is not an empty-group wait. A timeout means no further message was received during that wait, not that the broker has proved the group empty. The idle timeout does not itself release the group or expire the source. The negotiated `source.expiry-policy` and `source.timeout` settings remain unchanged.

A group delivery received before handover begins cancels the idle switch. The consumer handles that work before starting another idle wait. Deliveries arriving after handover begins still belong to the current assignment and must be resolved through the same buffer, settlement, and transaction rules as other cooperative handovers. The wait limits time spent waiting for more work, not the time needed to finish a safe handover.

With explicit acquisition, the consumer sends `pause`, resolves any deliveries received during handover and any outstanding settlement or transactions for that group, and sends `release` with the current `group-id` and `assignment-id`. After successful release, it sends `acquire` for the next eligible group. It MUST NOT treat a busy, failed, or unknown release as successful. The existing [unknown-outcome rules](#interruption) apply if an operation does not complete.

Without explicit acquisition, a consumer using `max-assignments=1` stops and confirms whole-link delivery, resolves any deliveries received during handover and any outstanding settlement or transactions, completes a closing detach, and attaches a fresh receiving source for broker assignment. It does not resume the abandoned source. If the broker assigns several groups to the same link, the consumer must close that link to give up an idle group. This ends all group assignments on the link, so the consumer must first stop delivery and resolve work for all those groups. With explicit acquisition, the consumer can instead use `pause` and `release` to give up only the idle group and keep receiving messages for the others.

The application must select whether the consumer cycles through groups. If the application requires messages from a specific group, the consumer MUST NOT switch to another group just because the idle wait expires. If no replacement work exists, an `acquire` request waits according to its existing [`wait` value](#acquisition-wait), or a consumer using broker assignment waits under credit. The broker may select the previous group again if new work arrived there; next-group acquisition does not define a fair rotation.

The [idle-switching example](#86-consumer-managed-idle-switching) shows the local wait followed by safe release and acquisition of the next group.

<a id="cooperative-takeover"></a>
#### 5.2.2 Cooperative group takeover

With explicit acquisition, a consumer can request a group held by another consumer. The broker asks its current owner to cooperate. The owner can refuse or resolve its work and release the group to the requester. Both consumers MUST use explicit acquisition, with `amqp:group-management-v1` selected on their receiving links; broker-assigned consumers do not participate in this exchange.

The requester sends `acquire` with a specific `group-id`, `takeover=true`, and a positive `wait` in seconds. It can also request `start-paused=true`. The broker checks consume rights, source filters, and assignment capacity before contacting the owner. A request for a group already held by the requesting source returns `invalid`. If the group has no owner when evaluated, ordinary acquisition rules apply, including the requirement for available messages.

For an owned group, the broker records the current `assignment-id` and requesting source, and generates a fresh UUID in `handover-id`. It binds that identifier to the logical node, group, old assignment, requesting source, and both current attachments. At most one handover may be pending for a group. Another takeover request returns `busy`; ordinary waiting acquisitions do not replace the pending requester.

The broker sends a `handover` notification to the owner on its receiving link, carrying the group, old assignment, and handover identifier. It does not expose the requester's principal or an address the owner must contact. The notification leaves ownership and delivery unchanged.

To decline, the owner sends `refuse` with those three identifiers and its own new `request-number`. A valid refusal returns `ok` to the owner and ends the requesting `acquire` with `unavailable` and `amqp:resource-locked`. If the owner has not selected explicit acquisition or its link is detached, the broker returns that acquisition failure without sending a notification.

To cooperate, the owner follows the existing [pause and work-resolution procedure](#handover), then sends `release` with the current group and assignment plus `handover-id`. Adding that identifier makes the release specific to this handover. A plain release keeps its existing meaning and cancels the pending takeover; it does not assign the group to that requester.

Before completing a handover-specific release, the broker MUST check that the same old assignment and both attachments still exist, the request has not expired, and the requester remains authorized and eligible. Its waiting slot must fit the actual assignment limit, and the new assignment must meet the [retained-inventory size limit](#recovery) where applicable. The owner must be paused, with no incomplete, unsettled, or unresolved transactional deliveries for the group. The broker returns `not-ready`, `busy`, or `limit` when the corresponding release condition is not met, without changing ownership; the takeover remains pending until resolved or cancelled.

Once these checks pass, the broker MUST remove the old assignment and create a fresh assignment on the requesting source in one ownership change. No other consumer can acquire the group between those actions. This can transfer an already assigned empty group, so later messages reach the requester. It does not permit ordinary acquisition of a new empty group.

The broker returns `ok` for the owner's release, echoing its old assignment and `handover-id`, and `ok` for the requesting acquisition with the fresh `assignment-id` and effective `start-paused` value. The acquisition result MUST precede new deliveries on the requesting link. Neither result waits for the other consumer to receive its result. The old consumer MUST NOT start further work from its earlier buffer after requesting this release unless a confirmed failure leaves its assignment valid and delivery is enabled.

The positive `wait` bounds the whole acquisition from broker receipt to assignment or refusal, including the owner's time to resolve work. It is not a group lease or a source-retention setting. Ordinary `acquire` still supports omitted, zero, and positive waits. The broker MUST NOT complete the takeover after its deadline or after ending the request, and MUST invalidate its `handover-id` on completion or cancellation.

Owner refusal, deadline expiry, a plain release, or another change to the old assignment cancels the pending handover. An observed detach or loss of either attachment, including authorized link stealing, also cancels it if the ownership change has not completed. The requester receives `unavailable` where a result can still be returned, with `amqp:resource-locked` while the original assignment is held, otherwise `amqp:not-found`. Loss of the requester's consume rights instead returns `denied`.

If the requester becomes ineligible before a handover-specific release completes, the broker cancels the handover and returns `unavailable` with `amqp:resource-locked` for that release. The old assignment remains held and paused. An expired or cancelled `handover-id` in a later `release` or `refuse` returns `stale`; it MUST NOT be treated as a plain release. The owner can send `permit` while its assignment remains valid.

Pending handovers are not retained across reattachment or broker restart. A cancelled request is not redirected to a later owner. The broker MUST prevent earlier attachment requests from completing after that cancellation. Completed assignments still follow their source's actual durability and expiry rules.

If either consumer's result is unknown, it follows [section 5.4](#interruption) rather than replaying the request or assuming that handover failed. A completed transfer is not undone because a result was lost: the old assignment is absent from the old source's recovered list, and the new assignment can be recovered on the requesting source if retained. Owner failure before consent follows [source lifetime and cleanup](#cleanup), not automatic assignment to the requester.

The [takeover example](#takeover-example) shows both owner-approved handover and refusal.

<a id="recovery"></a>
### 5.3 Resuming a link after an interruption

After an interruption, the consumer can resume the same logical link if the broker still retains its source and group assignments. The consumer reattaches using the same containers, link name, direction, and authorized principal, and supplies a non-null unsettled map even when empty. The broker MUST locate the actual retained source and group assignments or explicitly refuse resumption.

With broker-assigned consumption, the consumer and broker resolve unsettled deliveries using the existing AMQP resumption rules. The source keeps its group assignments. Once those rules allow new deliveries and credit is available, the broker can continue delivering messages without a `recover` or `permit` exchange.

With explicit acquisition, the consumer sends `recover` as its first group-control request after reattachment. Before building the response, the broker MUST resolve controls and waiting `acquire` requests from the previous attachment. Each earlier operation may have completed or been cancelled, but none can change the assignments after the broker builds the list returned by `recover`.

This includes cancelling any still-pending handover involving the previous attachment. `recover` returns retained assignments, not handover requests or `handover-id` values. A completed takeover is reflected by which source now holds the group.

The successful `recover` result lists every retained assignment in its `assignments` field, with its `group-id` and `assignment-id`. All listed assignments are paused, including groups that currently have no messages. A group released before the interruption is not listed. The consumer checks the returned group and assignment IDs against those it expects to hold, then sends `permit` for each group it is ready to receive.

The consumer and broker must also resolve unsettled deliveries under the core resumption rules before any new deliveries can start. If an expected `assignment-id` is missing from the list, that assignment has not been recovered. Neither side resends old requests or results. To acquire the group again, the consumer sends a new `acquire` request: the group must have available work, the broker generates a new `assignment-id`, and another consumer may acquire it first.

The complete `assignments` list returned by `recover` must fit in one Flow frame. For a source retained after a non-closing detach, the broker MUST check this before assigning another group. The check includes the full encoded response and Flow overhead, against the consumer's existing `open.max-frame-size` limit. If adding the group would make the response too large, the broker refuses that acquisition and keeps the existing assignments.

This size check also applies to a source using `session-end/0` while its session remains open. It does not apply to broker-assigned consumption or a source that expires on detach. If the consumer returns with a smaller frame-size limit and the list no longer fits, the broker refuses that resumption attempt without discarding retained state or extending its lifetime. The list is not split across multiple pages.

The consumer can resume the link through another gateway only if that gateway belongs to the same logical broker and can access the retained source and group assignments. If core link stealing is authorized, the consumer can attach the same logical link there while the previous attachment still exists. The broker closes the previous attachment and prevents its controls from making further changes. It keeps the retained source, which still follows its expiry policy and may lose state or require forced cleanup.

The consumer cannot use a different logical link to reclaim an existing assignment under this proposal. If it cannot restore the same logical link, it waits until the assignment ends through release, expiry, or loss before trying to acquire the group again.

The [interruption and recovery example](#84-waiting-interruption-and-recovery-with-explicit-acquisition) shows the broker returning retained assignments before delivery is enabled again.

<a id="interruption"></a>
### 5.4 When a group-control result is unknown

If the consumer times out waiting for a group-control result, it MUST stop sending controls on that attachment and treat pending operations as having unknown outcomes. If the session is usable, the consumer sends `detach(closed=false)` without an error. It waits for the broker's non-closing detach reply before trying to resume the retained link. If the broker replies with a closing detach, the source is abandoned instead.

If the detach exchange fails or times out but the connection is still usable, the consumer MUST end the affected session and complete the AMQP End exchange before resuming on another session. This also interrupts the session's other links and transactions. If the connection is unusable, the End exchange fails or times out, or core AMQP requires a connection error, the consumer terminates the connection. Merely sending detach or End, or deleting local request state, does not confirm that the broker has stopped controls from the old attachment.

These steps may cause the source to expire under its negotiated policy. For example, ending the session expires a `session-end/0` source, while a source with explicit retention may remain. The consumer MUST check that the source and assignments were actually retained before relying on recovery. It can instead abandon the source with a closing detach.

The [interruption and recovery example](#84-waiting-interruption-and-recovery-with-explicit-acquisition) shows how the consumer ends the old attachment before resuming.

<a id="cleanup"></a>
### 5.5 When a source is abandoned or an assignment is lost

When a source is abandoned or assignments are lost, the broker first disables the affected assignments and stops new deliveries for them. It MUST preserve known terminal and committed outcomes and respect legitimate message expiry and removal. Existing delivery records stay on their original link. Ending an assignment does not recall messages already delivered or transfer application state.

The broker also cancels pending handovers involving those assignments or that source. Failure or abandonment is not owner consent to assign a group directly to a requester; replacement acquisition follows the cleanup rules below.

If active local transactions involve the abandoned source, the broker first closes the coordinator control links used to create them. Under core AMQP, closing such a link rolls back every transaction created through it that has not yet committed or rolled back. This includes other work in those transactions, not just work from the abandoned source. An outcome already committed at the resource MUST NOT be rolled back.

Rollback can restore transactionally acquired messages even when their transfers were sent settled. This uses retained transaction state; it does not reconstruct lost pre-settled transfers outside transactional acquisition.

After resolving transactions, the broker destroys the abandoned source and settles its remaining delivery records. It applies the negotiated [`source.default-outcome`](#source-policies) only where the receiver's terminal outcome is unknown. Released can make the message available again; other negotiated outcomes follow their core rules. Before delivering returned messages again, the broker restores their positions as defined in [section 3.2](#delivery-order).

The error used to report assignment loss identifies the cause: `amqp:unauthorized-access` for revoked consume rights, `amqp:resource-deleted` for node deletion, or `amqp:internal-error` for assignment-state failure. If a request is still pending when the assignment is lost, the broker returns a failure result for that request if it can interpret the request and the attachment still exists. The result echoes the request's `request-number` and `operation` and includes the group fields required by [section 4.3](#control-values).

With explicit acquisition, the broker can report the loss of one group's assignment while leaving the link open. It first checks for incomplete, unsettled, or unresolved transactional deliveries for that group. If none remain, it sends the proposed `lost` notification after earlier transfers on the link. Other groups can continue.

If any such deliveries remain, the broker sends a closing detach with the loss cause, destroys the source of the consumer's receiving link, and invalidates every assignment on that source. Cleanup finishes before another acquisition can replace those assignments. They are not retained for recovery.

For broker-assigned consumption, the broker reports ownership loss with a closing detach when the consumer is reachable. It cannot report the loss of just one group while keeping that link open.

The broker MUST NOT wait indefinitely for a failed consumer to send dispositions or a final close reply before completing cleanup. Destroying the endpoint terminates incomplete transfers; input arriving afterward follows core errant-link and session-error rules. Assignments on independent sources remain held unless the transaction rollback or a required core session or connection error affects them. Cleanup and redelivery do not confirm that application work at an unreachable consumer has stopped.

<a id="sequences"></a>
## 6. Optional producer completion

### 6.1 Selecting bounded sequences

A bounded sequence lets the producer identify a set of messages within a group and mark its final message. The producer selects this proposed behavior by adding the sequence metadata defined in [section 6.2](#sequence-metadata) to those messages. Bounded and unbounded messages can coexist on the same node; the producer does not permanently mark a group as bounded. The proposal requires no queue-level enablement setting.

Producers and consumers using bounded sequences request and confirm the proposed [`amqp:group-sequences-v1` capability](#capability-selection) on their respective links. A consumer receiving only unbounded messages does not need this capability.

The application MUST ensure that any consumer that may receive its bounded-sequence messages supports them. This includes a consumer that already holds the group and any consumer that may acquire it later. Negotiating support between the producer and broker confirms support on that link or target, not support in the consumers. The proposal does not require the broker to exclude incompatible consumers from the node.

If a bounded message reaches a receiver that does not understand its annotation key, the existing AMQP [annotation-key rules](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#type-annotations) apply, as described in [section 6.3](#sequence-posting). The broker does not strip the metadata or bypass the group-ownership rules to deliver the message to a compatible consumer.

We propose carrying bounded-sequence metadata in the existing AMQP `message-annotations` section. Message annotations normally propagate through intermediaries with the message. [Section 8.5](#85-bounded-sequences-and-replies) shows a message with this metadata.

> **Considered alternative: delivery annotations**
>
> Delivery annotations apply to one link. Using them for sequence metadata would require every relevant hop to store the annotations and include them again on redelivery or forwarding.

<a id="sequence-metadata"></a>
### 6.2 Sequence identity and finality

For a bounded numbered sequence, include the proposed symbol key `amqp:group-sequence-v1` in the existing `message-annotations` section. Its value uses the proposed `group-sequence-info` type. The `sequence-id` field identifies the bounded sequence, and `final` marks its final original message:

<a id="listing-6"></a>
**Listing 6. Bounded-sequence metadata type.**

```xml
<type name="group-sequence-info" class="composite" source="list">
  <descriptor name="amqp:group-sequence-info-v1:list"/>
  <field name="sequence-id" type="uuid" mandatory="true"/>
  <field name="final" type="boolean" default="false"/>
</type>
```

Each message with this metadata MUST have the existing string `properties.group-id` (G) and `properties.group-sequence` for its position. The producer gives each bounded sequence a new UUID in the proposed `sequence-id` field, abbreviated S. It MUST NOT reuse that `sequence-id` for another sequence within the same node and group. Original messages are numbered from one, using core [RFC-1982 serial arithmetic](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transport-v1.0-os.html#type-sequence-no) when the number wraps. Restarting the number without changing `sequence-id` does not start a new sequence.

The producer sets `final=true` only on the last original message in the sequence. It MUST NOT send new original messages for that `sequence-id` afterward. If it retransmits a message, it keeps the same `group-id`, `sequence-id`, `group-sequence`, `final` value, and message identity. The existing `properties.message-id` remains optional. Retransmitting the final message of sequence S1 does not complete sequence S2 or release the group's assignment.

A grouped message without this annotation does not declare a bounded sequence. If the producer disappears before finishing sequence S, that sequence remains incomplete. The broker MUST NOT create a final indication or release the group because the producer disappeared. A final message can expire or be rejected, and receiving it does not prove that every earlier message was delivered or that processing succeeded.

<a id="sequence-posting"></a>
### 6.3 Posting and forwarding

Producers contributing to sequence S MUST coordinate their sends so its original messages are published in one order, using one of these paths:

- Earlier original messages have been accepted and made available in order before the final message is sent. Any transactions used to publish those earlier messages have committed successfully.
- Earlier original messages and the final message are sent in one ordered transaction. They become available only after that transaction commits successfully.

These conditions concern the broker accepting and publishing the producer's sends. They do not require the producer to wait for consumer processing or settlement.

Acceptance within a transaction is provisional until that transaction commits. Using the same `group-id` and `sequence-id` on independent links is not sufficient to order their sends. Different sequences may interleave in the order established by the receiving node.

The broker stores the interpreted metadata and preserves its meaning when it redelivers or forwards the message. Forwarding keeps the same `group-id`, `sequence-id`, `group-sequence`, `final` indication, and message identity. Each forwarder follows the publishing-order rule above. Each downstream node orders messages as they become available there; messages arriving through different paths do not acquire a common order across those paths.

The proposal adds no positional fields to the existing AMQP properties section.

If a message arrives unsettled with sequence metadata in `delivery-annotations`, malformed metadata, missing required `group-id`, `group-sequence`, or `sequence-id`, or incorrect field types, the receiver MUST reject it with `amqp:invalid-field`. If it cannot return an outcome, it detaches with that condition. A receiver that does not understand a proposed key follows the core [annotation-key rules](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html#type-annotations) instead of ignoring it as an optional `x-opt-` annotation.

<a id="alternatives"></a>
## 7. Alternatives and implementation precedents

These comparisons explain our choices; they do not add protocol requirements.

<a id="table-8"></a>
**Table VIII. Design choices.**

| Choice | What we propose and why | Alternative considered and why we did not choose it |
| --- | --- | --- |
| How groups are assigned | We propose [broker-assigned consumption](#ordinary) as the default. In that mode, the broker assigns a group before its first delivery, and the consumer reads `group-id` from the message without a separate acquisition request. [Explicit acquisition](#management) remains optional. | Requiring explicit acquisition for all grouped consumption would make every consumer request each group before receiving its messages. |
| How group-control requests are sent | With explicit acquisition, we use [Flow requests and results](#group-operations) on the consumer's receiving link. This supports one or several groups without a separate address for the control requests. An `acquire` request can name a group or ask for the next one. | Acquiring groups only through attach would require another link or negotiation for another group. Sending requests as application messages would require an address for the requests, a way to return replies, and message transfer credit. Having the broker offer groups would require rules for accepting or refusing each offer and choosing another consumer after refusal. |
| When delivery starts after acquisition | With explicit acquisition, we [enable delivery after successful acquisition](#group-operations) by default. A consumer that needs time to prepare requests `start-paused=true`, then sends `permit` when ready. Delivery still requires link credit. | Starting every acquisition paused would require an extra `permit` request even when the consumer is already ready. |
| Waiting for a group | With [broker-assigned consumption](#ordinary), the consumer waits with link credit. With explicit acquisition, we let [the acquire request wait by default](#acquisition-wait); the consumer can use `wait` to limit that time or request no wait. | Requiring every `acquire` request to return immediately would make the consumer repeat requests until a group becomes available. |
| Grouped and ungrouped messages | In both consumption modes, we [allow mixed delivery and optional grouped-only reception](#link-settings). Consumers can also use [supported filters that select complete groups](#source-policies). | Prohibiting mixed delivery or all filters would simplify which messages can be delivered, but applications needing those choices would require separate nodes or links. |
| Source lifetime and delivery outcomes | In both consumption modes, we use [the existing source fields](#source-policies) to say how long assignments are retained and what happens to unresolved deliveries. The consumer requests the values it needs and checks what the broker returns. | Requiring Released or `link-detach` for every source would prevent applications from choosing other supported outcomes or expiry policies. A separate group-retention duration could disagree with the source's lifetime. |
| Giving up a group | With explicit acquisition, the owner [pauses delivery and resolves its work](#handover). A plain release lets any eligible consumer acquire the group. For [cooperative takeover](#cooperative-takeover), the broker transfers it directly to the requester after the owner's handover-specific release. | Transferring ownership before the old work is resolved could let both consumers process it at once. A takeover request alone therefore does not release or move the group. |
| Resuming after an interruption | When the broker still holds the source and its assignments, a consumer using explicit acquisition [sends `recover`](#recovery). The broker returns every retained assignment, all paused. The consumer checks the list and resolves outstanding deliveries before enabling more work. | Automatically enabling every recovered group could deliver more messages before the consumer knows which earlier operations completed or which assignments it still holds. |
| Marking the final message | For bounded sequences, we use [a separate final field](#sequence-metadata) so `group-sequence` still gives the message's position. | Using the maximum `uint` value to mark the final message would use a sequence position as a completion flag as well. |
| Identifying a sequence | For bounded sequences, we [keep the group-id and give each sequence a new sequence-id](#sequence-metadata). The consumer can distinguish a new sequence from delayed messages belonging to an earlier one. | Using a new `group-id` for each sequence would avoid the extra sequence identifier, but later sequences would no longer belong to the same group and would need separate assignments. |
| Where sequence metadata goes | For bounded sequences, we put the metadata in [message-annotations](#sequences), which normally travel with the message through intermediaries. | Using `delivery-annotations` would require each relevant hop to store the metadata and include it again on redelivery or forwarding. |

The table below connects our choices to existing broker behavior and related AMQP specifications. These examples informed the proposal; they are not implementations of the extensions proposed here.

<a id="table-9"></a>
**Table IX. Implementation precedents.**

| Implementation or specification | What it shows |
| --- | --- |
| Service Bus / .NET 7.21.0 | For exclusive sessions, the .NET client can request a specific session or the next available one on a [dedicated receiving link](https://github.com/Azure/azure-sdk-for-net/blob/4e4c19469fe598b9f28a73d065514106985e7560/sdk/servicebus/Azure.Messaging.ServiceBus/src/Amqp/AmqpConnectionScope.cs#L699-L704). [SessionIdleTimeout](https://learn.microsoft.com/en-us/dotnet/api/azure.messaging.servicebus.servicebussessionprocessoroptions.sessionidletimeout?view=azure-dotnet) lets the processor try another session after waiting for a message. If the processor is configured to handle all specified sessions concurrently, the timeout limits each receive call without closing those sessions. |
| ActiveMQ Classic 6.4.0 | The [dispatch code](https://github.com/apache/activemq/blob/d0daf6310c82bd056be128264f4093b9fd9c236f/activemq-broker/src/main/java/org/apache/activemq/broker/region/Queue.java#L2367-L2412) assigns groups to consumers. A group-sequence value interpreted as negative inside the broker ends an existing assignment. If the group has no owner, that message creates an assignment instead. |
| Artemis 2.57.0 | The [dispatch code](https://github.com/apache/artemis/blob/20cab945f0944d669a0aac383a7578e2a6fd7346/artemis-server/src/main/java/org/apache/activemq/artemis/core/server/impl/QueueImpl.java#L3854-L3876) keeps a group with one consumer on a link that can hold several groups. The broker removes the assignment when it dispatches a message with the maximum AMQP `group-sequence` value. |
| RabbitMQ 4.4.0 | With single active consumer disabled, the linked [queue-consumer code](https://github.com/rabbitmq/rabbitmq-server/blob/24d5157cd415ef396c8ecd40a2d08c4d7ad3da9f/deps/rabbit/src/rabbit_queue_consumers.erl#L274-L301) selects consumers without a group-owner check. This contrasts with assigning each group to one consumer. |
| IBM MQ 9.4 documentation | The [JMS_IBM_Last_Msg_In_Group](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=messages-mapping-jms-provider-specific-fields) Boolean marks the last message in a group for point-to-point JMS/MQ messaging. The documented [AMQP mapping](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=mammf-mapping-amqp-fields-onto-mq-fields-incoming-messages) stores group fields as message properties rather than native MQ grouping fields. It rejects messages containing message annotations and discards delivery annotations. |
| Event Streams CSD01 | The [draft](https://docs.oasis-open.org/amqp/event-streams/v1.0/csd01/event-streams-v1.0-csd01.md) lets a consumer request a partition, one part of an event log, or let the node choose it. Choosing a partition is separate from exclusive ownership within a group of consumers. |

<a id="examples"></a>
## 8. Examples

These examples show broker-assigned consumption first, then explicit acquisition, handover, recovery, bounded sequences, idle switching, and cooperative takeover. Each uses only the capabilities needed for that exchange. Addresses and identifiers are fictional. The examples use existing AMQP frames and types with the proposed grouping fields; they do not add requirements.

Braces name fields in an illustrative frame or message. Control lists use the positions defined in [section 4.3](#control-values); words such as `request`, `acquire`, and `ok` denote symbols, request numbers denote `ulong`, and omitted trailing fields are null. Group IDs are strings; assignment and handover identifiers are UUIDs.

### 8.1 Broker-assigned consumption

This exchange follows the [broker-assignment rules](#ordinary), with the [source policies](#source-policies) described below.

<a id="listing-7"></a>
**Listing 7. Broker-assigned groups.**

```text
consumer -> broker: attach(
  name="worker", role=receiver,
  desired-capabilities=[symbol("amqp:message-groups-v1")],
  source={address:"work", distribution-mode:symbol("move")})
broker -> consumer: attach(
  name="worker", role=sender,
  offered-capabilities=[symbol("amqp:message-groups-v1")],
  source={address:"work", distribution-mode:symbol("move"),
          outcomes:[symbol("amqp:accepted:list"), symbol("amqp:released:list")],
          default-outcome:described(symbol("amqp:released:list"), [])})
consumer validates actual source; grants AMQP link credit
broker atomically assigns G before its first new acquiring transfer
broker -> consumer: message(properties={group-id:"G"}, body="work-1")
broker -> consumer: message(properties={}, body="ungrouped-work")
broker atomically assigns H before its first new acquiring transfer
broker -> consumer: message(properties={group-id:"H"}, body="other-group-work")
broker -> consumer: message(properties={group-id:"G"}, body="work-2")
```

Source durability, expiry, and timeout are omitted here, so their core defaults apply. Released is the outcome policy explicitly returned in this example, not a required default for all grouping sources. No assignment maximum was requested, so the link can hold G and H. The ungrouped message creates no assignment, and G remains assigned after work-1 settles. While no work is available, the consumer keeps waiting with credit rather than sending `acquire`, `permit`, or polling requests.

Using the same source policies, a consumer can instead request and confirm a one-group limit through the proposed [settings entry](#link-settings):

<a id="listing-8"></a>
**Listing 8. One-group link limit.**

```text
consumer -> broker: attach(properties={
  symbol("amqp:message-groups-v1"):
    described(symbol("amqp:group-settings-v1:list"), [false, uint(1)])}, ...)
broker -> consumer: attach(properties={
  symbol("amqp:message-groups-v1"):
    described(symbol("amqp:group-settings-v1:list"), [false, uint(1)])}, ...)
consumer validates the confirmed limit and source, then grants credit
```

The omitted attach fields are the same as in the preceding exchange. The one-group limit controls how many groups the link holds; the broker still chooses which group to assign.

<a id="explicit-acquisition-example"></a>
### 8.2 Explicit acquisition and optional preparation

The consumer selects [the required capabilities](#capability-selection), `amqp:message-groups-v1` and `amqp:group-management-v1`, for [explicit acquisition and optional preparation](#group-operations), then checks the returned settings and source. The control lists use positions `[kind, request-number, operation, group-id, assignment-id, status, error, assignments, wait, start-paused, takeover, handover-id]`. A1 and A2 represent distinct UUIDs. Every control is carried under the declared Flow key on the actual receiving-link handle, with valid current window state.

<a id="listing-9"></a>
**Listing 9. Explicit acquisition and preparation.**

```text
consumer -> broker: [request, 1, acquire, "G"]
broker -> consumer: [result, 1, acquire, "G", A1, ok, null, null, null, false]
broker may now deliver G using existing credit; no initial permit is needed

consumer -> broker:
  [request, 2, acquire, "H", null, null, null, null, seconds(30), true]
broker -> consumer:
  [result, 2, acquire, "H", A2, ok, null, null, null, true]
G continues; H remains paused while the consumer prepares it
consumer -> broker: [request, 3, permit, "H", A2]
broker -> consumer: [result, 3, permit, "H", A2, ok]
```

The first request [waits for G](#acquisition-wait) if it cannot be assigned immediately. The second lets the broker wait up to 30 seconds to assign H. A separate example shows a next-group request with `wait=0` when no eligible group is available:

<a id="listing-10"></a>
**Listing 10. Acquisition waiting.**

```text
consumer -> broker:
  [request, 1, acquire, null, null, null, null, null, seconds(0)]
broker -> consumer:
  [result, 1, acquire, null, null, unavailable, error("amqp:not-found")]
```

A successful result would instead include the selected `group-id`, a new `assignment-id`, and `start-paused=false`. The `unavailable` result ends the request without reserving a future assignment.

### 8.3 Ordered handover and busy release

Continuing the first exchange in [section 8.2](#explicit-acquisition-example), `old` is the consumer holding G with assignment A1 and H with A2. The label `new` identifies another eligible consumer.

<a id="listing-11"></a>
**Listing 11. Release and subsequent acquisition.**

```text
old -> broker: [request, 4, pause, "G", A1]
broker completes/aborts old partial G transfers, then:
broker -> old: [result, 4, pause, "G", A1, ok]
old resolves buffer and deliveries; a required settlement is still outstanding
old -> broker: [request, 5, release, "G", A1]
broker -> old: [result, 5, release, "G", A1, busy,
               error("amqp:precondition-failed")]
old finishes the settlement
old -> broker: [request, 6, release, "G", A1]
broker -> old: [result, 6, release, "G", A1, ok]
new -> broker: [request, 1, acquire, "G"]
broker -> new: [result, 1, acquire, "G", A3, ok, null, null, null, false]
```

This follows the [plain-release procedure](#handover), not cooperative takeover. H stays with the old consumer and remains enabled. The new consumer's `acquire` may wait if G is empty, and another eligible consumer may acquire G first. Success returns the fresh UUID A3. A release while delivery is enabled would return `not-ready`; a control naming old assignment A1 cannot remove A3.

### 8.4 Waiting interruption and recovery with explicit acquisition

This exchange follows the [unknown-result procedure](#interruption) and [retained-link recovery rules](#recovery).

In this separate exchange, a consumer using explicit acquisition holds H with assignment A2 and requests G. The broker assigns G with A3, but the consumer does not receive the successful result before its local timeout. The consumer requested, and the broker confirmed, `source.expiry-policy=link-detach`, `source.timeout=60`, and the actual outcome policy. Sixty seconds is illustrative:

<a id="listing-12"></a>
**Listing 12. Retained-link recovery after an unknown result.**

```text
consumer stops issuing controls on the old attachment
consumer -> broker: detach(closed=false, error=absent)
broker -> consumer: detach(closed=false, error=absent)
consumer resumes same authorized logical link within actual retention,
with a non-null core unsettled map (empty when no deliveries remain)
consumer -> broker: [request, 1, recover]
broker -> consumer: [result, 1, recover, null, null, ok, null,
                    [assignment("G", A3), assignment("H", A2)]]
consumer reconciles core deliveries and checks its groups; both are paused
consumer -> broker: [request, 2, permit, "G", A3]
broker -> consumer: [result, 2, permit, "G", A3, ok]
```

Here `assignment(G,A)` abbreviates the described [group-assignment value](#control-values). The result's `assignments` list contains every group still held by this source. A group released before interruption is absent. Before returning this list, the broker cancels requests from the previous attachment that are still waiting for a group; those requests cannot create an assignment afterward. If no assignments survive, the list is empty.

If the detach exchange does not finish but the connection is usable, the consumer completes the End exchange for that session first. If that exchange fails or the connection is unusable, it terminates the connection. The source may expire before recovery. If this example used the default `session-end/0`, ending the session would expire it. The consumer needs a successful response to confirm which assignments were recovered.

### 8.5 Bounded sequences and replies

In this example, the application ensures that every consumer that may receive these messages supports bounded sequences. The producer and those consumers confirm the [proposed sequence capability](#capability-selection) on their respective links. Group G can contain sequence S1 with positions 1, 2, and 3, where 3 has `final=true`, followed by sequence S2 with positions 1 and 2, where 2 has `final=true`. Each [metadata value](#sequence-metadata) is `described(symbol("amqp:group-sequence-info-v1:list"), [S, final])`, under the proposed symbol key `amqp:group-sequence-v1` in `message-annotations`.

The following message is the final original message of S1, at position 3. The UUID below identifies S1.

<a id="listing-13"></a>
**Listing 13. Bounded-sequence final message.**

```text
producer -> broker: message(
  properties={group-id:"G", group-sequence:sequence-no(3)},
  message-annotations={
    symbol("amqp:group-sequence-v1"):
      described(symbol("amqp:group-sequence-info-v1:list"),
        [uuid("f494adb7-7107-4cad-9b20-39de1a8c0766"), true])
  },
  body="work-3")
```

A retransmitted final message for S1 still identifies S1; it does not complete S2 or release G. [Earlier original messages must be available before the final message](#sequence-posting), or be included with it in one ordered transaction that commits successfully. If that transaction rolls back, the final message does not become available. Group G can stay assigned to the source of the same receiving link throughout both sequences.

A request can set `reply-to="responses"` and `reply-to-group-id="response-G"`. Where the [application binding](#33-replies-and-status-streams) uses that requested reply group, replies and status messages carry outgoing `group-id="response-G"` and the binding's existing correlation value. A response consumer can receive a broker-assigned group or use explicit acquisition on its link. Work and response assignments are independent. Ordinary acquisition does not reserve an unowned empty response group.

### 8.6 Consumer-managed idle switching

In this separate exchange, the application has selected next-group cycling and a local idle wait. With explicit acquisition, a consumer holding G with A1 can reuse the existing controls after the wait expires:

<a id="listing-14"></a>
**Listing 14. Consumer idle switching.**

```text
consumer finishes G's buffered and active work and waits locally for another G message
no G message arrives before its configured receive-idle wait expires
consumer -> broker: [request, 4, pause, "G", A1]
broker completes/aborts partial G transfers, then:
broker -> consumer: [result, 4, pause, "G", A1, ok]
consumer resolves any G deliveries that arrived during handover
consumer -> broker: [request, 5, release, "G", A1]
broker -> consumer: [result, 5, release, "G", A1, ok]
consumer -> broker: [request, 6, acquire]
broker -> consumer: [result, 6, acquire, "H", A2, ok, null, null, null, false]
```

The final request selects the next eligible group because G is omitted. It may wait, and success could name G again if G has new work. The [idle-switching rules](#idle-switching) also define the closing-detach/fresh-attach path for broker assignment on a one-group link. Neither path adds a broker idle timer or proves the queue empty.

<a id="takeover-example"></a>
### 8.7 Cooperative group takeover

This exchange follows the [cooperative-takeover rules](#cooperative-takeover).

Both consumers have selected explicit acquisition. The owner holds group G with assignment A1 and another group H. The requester asks for G with a 30-second handover deadline and initial pause. A1, A3, and T1 represent distinct UUIDs; T1 identifies this pending handover.

<a id="listing-15"></a>
**Listing 15. Cooperative group takeover.**

```text
requester -> broker:
  [request, 1, acquire, "G", null, null, null, null, seconds(30), true, true]
broker -> owner:
  [handover, null, null, "G", A1, null, null, null, null, null, null, T1]
owner -> broker: [request, 4, pause, "G", A1]
broker completes or aborts partial G transfers, then:
broker -> owner: [result, 4, pause, "G", A1, ok]
owner resolves G's work, buffered deliveries, settlement, and transactions
owner -> broker:
  [request, 5, release, "G", A1, null, null, null, null, null, null, T1]
broker validates both attachments, the deadline, and release conditions
broker replaces A1 with A3 on the requesting source without an unowned interval
broker -> owner:
  [result, 5, release, "G", A1, ok, null, null, null, null, null, T1]
broker -> requester:
  [result, 1, acquire, "G", A3, ok, null, null, null, true]
requester -> broker: [request, 2, permit, "G", A3]
broker -> requester: [result, 2, permit, "G", A3, ok]
```

The owner keeps H. G can be empty at handover; its later messages go to A3's receiving link once delivery is enabled and credit is available. The broker creates A3 before either consumer receives its result, so their result arrival order is not guaranteed.

Instead of cooperating, the owner can refuse using the same notification:

<a id="listing-16"></a>
**Listing 16. Takeover refusal.**

```text
owner -> broker:
  [request, 4, refuse, "G", A1, null, null, null, null, null, null, T1]
broker -> owner:
  [result, 4, refuse, "G", A1, ok, null, null, null, null, null, T1]
broker -> requester:
  [result, 1, acquire, "G", null, unavailable, error("amqp:resource-locked")]
```

Refusal keeps A1 and its delivery state unchanged. If the 30-second deadline expires instead, the acquisition ends without transfer; a later release naming T1 returns `stale`. A result lost after a completed handover follows the [unknown-outcome procedure](#interruption) and [recovery rules](#recovery), not a replay or an automatic reversal.

<a id="security-considerations"></a>
## 9. Safety, Security, and Data Protection Considerations

The [authorization and control-matching rules](#control-errors) define the identity and assignment checks for group controls. The [takeover rules](#cooperative-takeover) define owner consent and handover-identifier validation. [Source abandonment and assignment loss](#cleanup) define cleanup and the limits of reassignment when a consumer is unreachable.

<a id="conformance"></a>
## 10. Conformance

The requirements depend on the role and capabilities selected. Base grouping uses broker assignment. Selecting explicit acquisition adds the group-control requirements, including cooperative takeover. Bounded-sequence support is independently optional. The links below identify the defining sections; this table summarizes their obligations.

<a id="table-10"></a>
**Table X. Conformance clauses.**

| Clause | Role or selected capability | Obligations |
| --- | --- | --- |
| C-01 | Broker and consumer implementing base grouping | [Confirm support and receiving-source settings](#negotiation). The broker supports shared links and a requested one-group limit, and assigns groups before delivery; the consumer checks the returned settings and grants credit. Both follow the [ownership and delivery-order rules](#ordinary) and [source lifetime and cleanup rules](#lifetime). |
| C-02 | Broker and consumer selecting explicit acquisition | Follow the [control layouts](#control-values), authorization, result matching, and error rules. Assign groups only through successful `acquire` requests. Support the defined acquisition, preparation, waiting, pause, release, refusal, and [retained-link recovery](#recovery) behavior. |
| C-03 | Broker and both consumers participating in cooperative takeover | Follow [section 5.2.2](#cooperative-takeover). Obtain owner consent through a valid handover-specific release, resolve old work and delivery state, and transfer directly to the requester with a fresh assignment. Honor the deadline, source limits, cancellation, stale-identifier, and unknown-result rules. |
| C-04 | Producer, broker, and consumer selecting bounded-sequence support | [Confirm sequence support](#sequences) and use `message-annotations` for the defined metadata. Follow [sequence identity and finality](#sequence-metadata) and [publication, validation, and forwarding rules](#sequence-posting). Messages without this metadata remain unbounded. |
| C-05 | Application using bounded sequences | Ensure that [every possible recipient supports the metadata](#sequences), including current and future group owners. Confirmation between producer and broker alone does not establish support in consumers. |
| C-06 | Forwarder | Follow the applicable producer and broker rules at each hop. [Preserve group properties, sequence metadata, and publication order](#sequence-posting) when forwarding bounded messages. |
| C-07 | Consumer selecting idle switching | Follow the [consumer idle policy](#idle-switching) and the handover path for its consumption mode. Keep the idle wait separate from source retention and acquisition waiting. Do not switch a required group or abandon other groups' active work because one group is quiet. |

<a id="license-notices"></a>
## Annex A. License, Document Status and Notices

(This annex forms an integral part of this Specification.)

### A.1 Document Status

This is an unapproved contributor working draft prepared for discussion by the OASIS Advanced Message Queuing Protocol (AMQP) TC. The date on the cover identifies this working draft, not a committee approval.

TC members should send comments to the TC's general email list. Others should use the [TC's public comment facility](https://groups.oasis-open.org/communities/community-home?communitykey=f83ec4e4-c2ad-4e1f-b9d2-018f5aa7a390) after obtaining access through the [comment signup form](https://www.oasis-open.org/comment-signup/) and accepting the OASIS Feedback License.

The normative XML type definitions are provided in the separate file referenced in [Annex C](#machine-readable-definitions). If a definition in that file differs from its display in this document, the definition in the separate file prevails.

### A.2 License and Notices

Copyright © OASIS Open 2026. All Rights Reserved.

All capitalized terms in the following text have the meanings assigned to them in the OASIS Intellectual Property Rights Policy (the "OASIS IPR Policy"). The full Policy, which governs the licensure of this document, may be found at the OASIS website: <https://www.oasis-open.org/policies-guidelines/ipr/>.

This document and translations of it may be copied and furnished to others, and derivative works that comment on or otherwise explain it or assist in its implementation may be prepared, copied, published, and distributed, in whole or in part, without restriction of any kind, provided that the above copyright notice and this section are included on all such copies and derivative works. However, this document itself may not be modified in any way, including by removing the copyright notice or references to OASIS, except as needed for the purpose of developing any document or deliverable produced by an OASIS Technical Committee (in which case the rules applicable to copyrights, as set forth in the OASIS IPR Policy, must be followed) or as required to translate it into languages other than English.

The limited permissions granted above are perpetual and will not be revoked by OASIS or its successors or assigns, as provided in the OASIS IPR Policy.

This document is provided under the RF on RAND IPR mode that was chosen when the project was established, as defined in the IPR Policy. For information on whether any patents have been disclosed that may be essential to implementing this document, and any offers of patent licensing terms, please refer to the [Intellectual Property Rights section of the TC's web page](https://www.oasis-open.org/committees/amqp/ipr.php).

This document and the information contained herein is provided on an "AS IS" basis and OASIS DISCLAIMS ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTY THAT THE USE OF THE INFORMATION HEREIN WILL NOT INFRINGE ANY OWNERSHIP RIGHTS OR ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. OASIS AND ITS MEMBERS WILL NOT BE LIABLE FOR ANY DIRECT, INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF ANY USE OF THIS DOCUMENT OR ANY PART THEREOF.

The name "OASIS" is a trademark of OASIS, the owner and developer of this document, and should be used only to refer to the organization and its official outputs. OASIS welcomes reference to, and implementation and use of, its documents, while reserving the right to enforce its marks against misleading uses. Please see <https://www.oasis-open.org/policies-guidelines/trademark/> for guidance.

<a id="references"></a>
## Annex B. References

(This annex forms an integral part of this Specification.)

<a id="foundations"></a>
### B.1 Normative foundations

- OASIS AMQP Version 1.0, 29 October 2012: [Types](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-types-v1.0-os.html), [Transport](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transport-v1.0-os.html), [Messaging](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html) and [Transactions](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transactions-v1.0-os.html). Their authoritative XML documents are [Types XML](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-types-v1.0-os.xml), [Transport XML](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transport-v1.0-os.xml), [Messaging XML](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.xml) and [Transactions XML](https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-transactions-v1.0-os.xml).
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119.html) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174.html), BCP 14.
- [RFC 1982](https://www.rfc-editor.org/rfc/rfc1982.html), Serial Number Arithmetic.

### B.2 Background references

The [implementation precedents](#alternatives) link their supporting sources at the point of use. Those precedents are version-specific evidence, not implementations of the proposed extension.

<a id="machine-readable-definitions"></a>
## Annex C. Machine-Readable Definitions

(This annex forms an integral part of this Specification.)

[message-groups-types.xml](message-groups-types.xml) contains the `group-settings`, `group-control`, `group-assignment`, and `group-sequence-info` definitions displayed in sections 2.2, 4.3, and 6.2. It uses the AMQP specification's XML type-definition format; the field types are defined by the [AMQP core specifications](#foundations).

<a id="acknowledgments"></a>
## Appendix 1. Acknowledgments

(This appendix does not form an integral part of this Specification and is informational.)

None.

<a id="revision-history"></a>
## Appendix 2. Changes From Previous Version

(This appendix does not form an integral part of this Specification and is informational.)

Initial contribution. No previous published version.

<a id="table-11"></a>
**Table XI. Revision history.**

| Date | Revision |
| --- | --- |
| 2026-11-24 | Working Draft 01. |
