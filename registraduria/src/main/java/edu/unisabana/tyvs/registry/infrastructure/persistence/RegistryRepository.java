package edu.unisabana.tyvs.registry.infrastructure.persistence;

import edu.unisabana.tyvs.registry.application.port.out.RegistryRepositoryPort;
import java.sql.*;
import java.util.Optional;
import javax.sql.DataSource;

public class RegistryRepository implements RegistryRepositoryPort {
    private final String jdbcUrl;
    private final String username;
    private final String password;

    /**
     * Pool de conexiones (HikariCP). Si es null, se usa DriverManager y se abre
     * una conexion nueva en cada operacion (comportamiento original, sin pool).
     *
     * Se deja la opcion sin pool a proposito: permite medir el "antes" y el
     * "despues" con el MISMO jar, cambiando solo una propiedad
     * (registry.pool.max-size=0). Asi la comparacion mide solo el efecto del pool.
     */
    private final DataSource dataSource;

    public RegistryRepository(String jdbcUrl) {
        this(jdbcUrl, "", "");
    }

    public RegistryRepository(String jdbcUrl, String username, String password) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.password = password;
        this.dataSource = null;
    }

    /** Variante con pool: las conexiones se toman prestadas y se devuelven al cerrar. */
    public RegistryRepository(DataSource dataSource) {
        this.jdbcUrl = null;
        this.username = null;
        this.password = null;
        this.dataSource = dataSource;
    }

    private Connection getConnection() throws SQLException {
        if (dataSource != null) {
            // con pool: close() devuelve la conexion al pool, no la destruye
            return dataSource.getConnection();
        }
        // sin pool: conexion nueva en cada operacion (defecto PERF-01)
        return DriverManager.getConnection(jdbcUrl, username, password);
    }

    @Override
    public void initSchema() throws Exception {
        final String ddl = "CREATE TABLE IF NOT EXISTS registry(" +
                " id INT PRIMARY KEY," +
                " name VARCHAR(100) NOT NULL," +
                " age INT NOT NULL," +
                " is_alive BOOLEAN NOT NULL" +
                ");";
        try (Connection con = getConnection(); Statement st = con.createStatement()) {
            st.execute(ddl);
        }
    }

    @Override
    public boolean existsById(int id) throws Exception {
        final String sql = "SELECT 1 FROM registry WHERE id = ?";
        try (Connection con = getConnection(); PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setInt(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }

    @Override
    public void save(int id, String name, int age, boolean isAlive) throws Exception {
        final String sql = "INSERT INTO registry(id, name, age, is_alive) VALUES(?, ?, ?, ?)";
        try (Connection con = getConnection(); PreparedStatement ps = con.prepareStatement(sql)) {
            boolean prev = con.getAutoCommit();
            con.setAutoCommit(false);
            try {
                ps.setInt(1, id);
                ps.setString(2, name);
                ps.setInt(3, age);
                ps.setBoolean(4, isAlive);
                ps.executeUpdate();
                con.commit();
            } catch (SQLException e) {
                con.rollback();
                throw e;
            } finally {
                con.setAutoCommit(prev);
            }
        }
    }

    @Override
    public Optional<RegistryRecord> findById(int id) throws Exception {
        final String sql = "SELECT id, name, age, is_alive FROM registry WHERE id = ?";
        try (Connection con = getConnection(); PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setInt(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next())
                    return Optional.empty();
                return Optional.of(new RegistryRecord(
                        rs.getInt("id"),
                        rs.getString("name"),
                        rs.getInt("age"),
                        rs.getBoolean("is_alive")));
            }
        }
    }

    @Override
    public void deleteAll() throws Exception {
        try (Connection con = getConnection(); Statement st = con.createStatement()) {
            st.executeUpdate("DELETE FROM registry");
        }
    }
}
