package com.example.util;

/** ADR-0006: a utility class is final, so it stays a namespace rather than becoming a type. */
public final class StringUtils {

    // VIOLATES ADR-0004: util -> controller closes a cycle back through service.
    private static final com.example.controller.OrderController CONTROLLER = null;

    private StringUtils() {
    }

    public static String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
