package com.deviceagent.domain;

public enum ExecutionStatus {
    PROPOSED,
    AUTHORIZED,
    REJECTED,
    CANCELLED_BEFORE_DISPATCH,
    PREPARED,
    DISPATCHED,
    ACKNOWLEDGED,
    APPLIED,
    NOT_APPLIED,
    UNKNOWN,
    BLOCKED,
    SKIPPED
}
