package edu.unisabana.tyvs.registry.config;

import edu.unisabana.tyvs.registry.application.port.out.RegistryRepositoryPort;
import edu.unisabana.tyvs.registry.application.usecase.Registry;
import edu.unisabana.tyvs.registry.infrastructure.persistence.RegistryRepository;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Cableado de la aplicacion (composition root).
 *
 * La URL JDBC se lee de una propiedad, con un valor por defecto, en vez de
 * estar escrita en el codigo. No es cosmetico: permite que cada prueba de
 * integracion use su propia base en memoria y no contamine a las demas, y
 * evita tener que declarar beans alternativos en la prueba.
 *
 * Ese ultimo punto tiene una trampa que costo un build en rojo: si una prueba
 * declara un @TestConfiguration con un @Bean llamado igual que uno de aqui
 * (el nombre del bean es el nombre del METODO), Spring aborta el arranque con
 * BeanDefinitionOverrideException. Parametrizar la URL hace innecesarios esos
 * beans duplicados.
 */
@Configuration
public class RegistryConfig {

    /**
     * Repositorio con o sin pool de conexiones.
     *
     * registry.pool.max-size > 0  -> HikariCP con ese tamano maximo (por defecto 20).
     * registry.pool.max-size = 0  -> sin pool: conexion nueva por operacion
     *                                (el comportamiento original, para medir el "antes").
     *
     * El pool se registra en Micrometer, asi que Actuator expone
     * hikaricp.connections.active / pending / usage: se puede ver desde el
     * servidor si el pool se queda corto bajo carga.
     */
    @Bean
    public RegistryRepositoryPort registryRepositoryPort(
            @Value("${registry.jdbc-url:jdbc:h2:mem:regdb;DB_CLOSE_DELAY=-1}") String jdbcUrl,
            @Value("${registry.pool.max-size:20}") int poolMaxSize,
            ObjectProvider<MeterRegistry> meterRegistry)
            throws Exception {
        RegistryRepository repo;
        if (poolMaxSize > 0) {
            HikariConfig cfg = new HikariConfig();
            cfg.setPoolName("registry-pool");
            cfg.setJdbcUrl(jdbcUrl);
            cfg.setMaximumPoolSize(poolMaxSize);
            MeterRegistry registry = meterRegistry.getIfAvailable();
            if (registry != null) {
                cfg.setMetricRegistry(registry);
            }
            repo = new RegistryRepository(new HikariDataSource(cfg));
        } else {
            repo = new RegistryRepository(jdbcUrl);
        }
        repo.initSchema();
        return repo;
    }

    @Bean
    public Registry registry(RegistryRepositoryPort port) {
        return new Registry(port);
    }
}
