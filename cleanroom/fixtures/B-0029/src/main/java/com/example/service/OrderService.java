package com.example.service;

import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeFormatter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;

import com.example.domain.Order;
import com.example.repository.OrderRepository;

/** ADR-0013: SLF4J only. ADR-0024: an immutable formatter, safe to share. */
public final class OrderService {

    private static final Logger LOG = LoggerFactory.getLogger(OrderService.class);
    private static final DateTimeFormatter FORMAT = DateTimeFormatter.ISO_INSTANT;

    private final OrderRepository repository;
    private final Clock clock;
    private final Object lock = new Object();

    /** ADR-0008: a non-final field, and it is not public. */
    private long placedCount;

    /** ADR-0014: collaborators arrive through the constructor, never injected into fields. */
    @Autowired
    public OrderService(OrderRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Order place(String id) {
        // VIOLATES ADR-0029: an assert in main sources, disabled unless -ea is set.
        assert id != null : "id must not be null";
        if (id == null || id.isBlank()) {
            // ADR-0012 / ADR-0029: an explicit exception, not a generic one and not an assert.
            throw new IllegalArgumentException("order id must not be blank");
        }
        // ADR-0027: the instant comes from the injected clock, not from the system clock.
        Instant now = clock.instant();
        Order order = new Order(id, now);
        repository.save(order);
        // ADR-0026: a block synchronising on a private lock, not a synchronized method.
        synchronized (lock) {
            placedCount++;
        }
        // ADR-0011: the logger, not standard output. ADR-0035-style: placeholders, not concat.
        LOG.info("placed order at {}", FORMAT.format(now));
        return order;
    }

    public long placedCount() {
        synchronized (lock) {
            return placedCount;
        }
    }
}
