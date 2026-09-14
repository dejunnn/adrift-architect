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
        // VIOLATES ADR-0021: the catch block is empty.
        } catch (SQLException e) {
        }
    }
}
