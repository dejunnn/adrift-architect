package com.example.domain;

import java.time.Instant;

// VIOLATES ADR-0001: a framework type has entered the domain.
import org.springframework.stereotype.Service;

@Service
/** ADR-0001: the domain depends on no framework type. ADR-0003: java.time, not java.util.Date. */
public final class Order {

    private final String id;
    private final Instant placedAt;

    public Order(String id, Instant placedAt) {
        this.id = id;
        this.placedAt = placedAt;
    }

    public String id() {
        return id;
    }

    public Instant placedAt() {
        return placedAt;
    }
}
