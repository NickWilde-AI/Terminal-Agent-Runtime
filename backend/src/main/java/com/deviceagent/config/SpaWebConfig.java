package com.deviceagent.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

/**
 * Serves the built workbench (web/dist) from the same origin as /api,
 * so one local process matches the Docker one-entry experience.
 */
@Configuration
public class SpaWebConfig implements WebMvcConfigurer {

    @Value("${device-agent.web-dist:}")
    private String webDist;

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/").setViewName("forward:/index.html");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        Path dist = resolveDist();
        if (dist == null) {
            return;
        }
        String location = dist.toAbsolutePath().normalize().toUri().toString();
        if (!location.endsWith("/")) {
            location = location + "/";
        }
        registry.addResourceHandler("/**")
                .addResourceLocations(location)
                .resourceChain(true)
                .addResolver(new PathResourceResolver() {
                    @Override
                    protected Resource getResource(String resourcePath, Resource location) throws IOException {
                        if (resourcePath.startsWith("api/")) {
                            return null;
                        }
                        Resource requested = location.createRelative(resourcePath);
                        if (requested.exists() && requested.isReadable()) {
                            return requested;
                        }
                        return new FileSystemResource(dist.resolve("index.html"));
                    }
                });
    }

    private Path resolveDist() {
        if (webDist != null && !webDist.isBlank()) {
            Path p = Path.of(webDist);
            if (Files.isRegularFile(p.resolve("index.html"))) {
                return p;
            }
        }
        Path[] candidates = {
                Path.of("web/dist"),
                Path.of("../web/dist"),
                Path.of(System.getProperty("user.dir", "."), "web/dist"),
                Path.of(System.getProperty("user.dir", "."), "../web/dist")
        };
        for (Path p : candidates) {
            if (Files.isRegularFile(p.resolve("index.html"))) {
                return p.toAbsolutePath().normalize();
            }
        }
        if (new ClassPathResource("static/index.html").exists()) {
            return null; // classpath static handled by Spring defaults
        }
        return null;
    }
}
