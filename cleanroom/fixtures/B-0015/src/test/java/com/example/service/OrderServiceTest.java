package com.example.service;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import com.example.domain.Order;
import com.example.persistence.OrderDao;
import com.example.repository.OrderRepository;

/** ADR-0007: @Test methods live in a class whose simple name ends in Test. */
public class OrderServiceTest {

    @Test
    void placesAnOrderAtTheInjectedInstant() {
        Clock fixed = Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);
        OrderService service = new OrderService(new OrderRepository(new OrderDao(null)), fixed);
        Order order = service.place("A-1");
        // ADR-0015: the assertion says which invariant it guards.
        // VIOLATES ADR-0015: an assertion with no detail message.
        assert order.placedAt().equals(fixed.instant());
    }
}
