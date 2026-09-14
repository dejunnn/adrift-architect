package com.example.controller;

import com.example.domain.Order;
import com.example.service.OrderService;
import com.example.util.StringUtils;

/** ADR-0002: the controller reaches the service, never the repository. */
public final class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public Order place(String id) {
        // controller -> util. One-way, so no cycle: ADR-0004 holds. It is also what lets the
        // ADR-0004 variant close a loop with a single edit on the util side.
        return service.place(StringUtils.trimToEmpty(id));
    }
}
