package com.example.persistence;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import com.example.domain.Order;

/** ADR-0009: the only class permitted to see java.sql. */
public final class OrderDao {

    private final Connection connection;

    public OrderDao(Connection connection) {
        this.connection = connection;
    }

    public void insert(Order order) {
        // ADR-0021: the catch block has a body. ADR-0030: it names a specific type.
        try (PreparedStatement statement =
                 connection.prepareStatement("INSERT INTO orders (id) VALUES (?)")) {
            statement.setString(1, order.id());
            statement.executeUpdate();
        // VIOLATES ADR-0030: catching Throwable also catches Error.
        } catch (Throwable e) {
            // ADR-0012: a named failure, not a generic one. ADR-0028: not printStackTrace.
            throw new IllegalStateException("could not insert order " + order.id(), e);
        }
    }
}
