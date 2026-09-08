package com.deviceagent.domain;

public enum RunLifecycle {
    RECEIVED,
    RUNNING,
    WAITING_CLARIFICATION,
    WAITING_CONFIRMATION,
    COMPLETED,
    PARTIAL,
    FAILED,
    STOPPED,
    CANCELLED,
    TIMED_OUT,
    INTERRUPTED
}
