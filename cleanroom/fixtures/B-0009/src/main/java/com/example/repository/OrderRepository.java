package com.example.repository;

import com.example.domain.Order;
import com.example.persistence.OrderDao;

/** ADR-0009: the repository owns no java.sql type; the DAO does. */
public final class OrderRepository {

    // VIOLATES ADR-0009: a java.sql type outside ..persistence..
    private final java.sql.Connection connection = null;
    private final OrderDao dao;

    public OrderRepository(OrderDao dao) {
        this.dao = dao;
    }

    public void save(Order order) {
        dao.insert(order);
    }
}
