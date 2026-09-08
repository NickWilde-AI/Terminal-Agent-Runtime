package com.deviceagent.memory;

import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.Ids;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * SQLite-backed long-term memory with in-memory fallback for tests.
 */
@Component
public class MemoryStore {
    private final DeviceAgentProperties properties;
    private final Path dbPath;
    private final List<MemoryEntry> memoryFallback = new CopyOnWriteArrayList<>();
    private volatile boolean useSqlite;

    public MemoryStore(DeviceAgentProperties properties) {
        this.properties = properties;
        this.dbPath = Path.of(properties.getSqlitePath());
    }

    @PostConstruct
    public void init() throws Exception {
        useSqlite = "sqlite".equalsIgnoreCase(properties.getPersistence());
        if (!useSqlite) {
            return;
        }
        Files.createDirectories(dbPath.getParent() == null ? Path.of(".") : dbPath.getParent());
        try (Connection c = conn(); Statement st = c.createStatement()) {
            st.execute("""
                    create table if not exists memories (
                      id text primary key,
                      session_id text not null,
                      category text not null,
                      key text not null,
                      value text not null,
                      domain text not null,
                      source_run_id text not null,
                      created_at text not null,
                      confidence real not null,
                      hit_count integer not null,
                      last_hit_at text,
                      active integer not null,
                      note text
                    )
                    """);
        }
    }

    public MemoryEntry save(MemoryEntry entry) {
        if (entry.getId() == null || entry.getId().isBlank()) {
            entry.setId(Ids.newId("mem"));
        }
        if (entry.getCreatedAt() == null) {
            entry.setCreatedAt(Ids.now());
        }
        if (!useSqlite) {
            // deactivate older same key
            memoryFallback.stream()
                    .filter(m -> m.isActive()
                            && m.getSessionId().equals(entry.getSessionId())
                            && m.getKey().equals(entry.getKey()))
                    .forEach(m -> m.setActive(false));
            memoryFallback.add(entry);
            return entry;
        }
        try (Connection c = conn()) {
            try (PreparedStatement deactivate = c.prepareStatement(
                    "update memories set active=0 where session_id=? and key=? and active=1")) {
                deactivate.setString(1, entry.getSessionId());
                deactivate.setString(2, entry.getKey());
                deactivate.executeUpdate();
            }
            try (PreparedStatement ps = c.prepareStatement("""
                    insert into memories(id,session_id,category,key,value,domain,source_run_id,created_at,
                      confidence,hit_count,last_hit_at,active,note)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """)) {
                bind(ps, entry);
                ps.executeUpdate();
            }
        } catch (Exception ex) {
            throw new IllegalStateException("memory save failed: " + ex.getMessage(), ex);
        }
        return entry;
    }

    public List<MemoryEntry> listActive(String sessionId) {
        if (!useSqlite) {
            return memoryFallback.stream()
                    .filter(m -> m.isActive() && sessionMatches(m, sessionId))
                    .sorted(Comparator.comparing(MemoryEntry::getCreatedAt).reversed())
                    .toList();
        }
        List<MemoryEntry> out = new ArrayList<>();
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement(
                     "select * from memories where active=1 and session_id=? order by created_at desc")) {
            ps.setString(1, sessionId == null ? "local" : sessionId);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    out.add(fromRs(rs));
                }
            }
        } catch (Exception ex) {
            throw new IllegalStateException("memory list failed: " + ex.getMessage(), ex);
        }
        return out;
    }

    public List<MemoryEntry> listHistory(String sessionId, String key) {
        if (!useSqlite) {
            return memoryFallback.stream()
                    .filter(m -> sessionMatches(m, sessionId) && m.getKey().equals(key))
                    .sorted(Comparator.comparing(MemoryEntry::getCreatedAt).reversed())
                    .toList();
        }
        List<MemoryEntry> out = new ArrayList<>();
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement(
                     "select * from memories where session_id=? and key=? order by created_at desc")) {
            ps.setString(1, sessionId == null ? "local" : sessionId);
            ps.setString(2, key);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    out.add(fromRs(rs));
                }
            }
        } catch (Exception ex) {
            throw new IllegalStateException("memory history failed: " + ex.getMessage(), ex);
        }
        return out;
    }

    public Optional<MemoryEntry> findById(String id) {
        if (!useSqlite) {
            return memoryFallback.stream().filter(m -> m.getId().equals(id)).findFirst();
        }
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement("select * from memories where id=?")) {
            ps.setString(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return Optional.of(fromRs(rs));
                }
            }
        } catch (Exception ex) {
            throw new IllegalStateException("memory find failed: " + ex.getMessage(), ex);
        }
        return Optional.empty();
    }

    public boolean softDelete(String id) {
        if (!useSqlite) {
            Optional<MemoryEntry> found = findById(id);
            found.ifPresent(m -> m.setActive(false));
            return found.isPresent();
        }
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement("update memories set active=0 where id=?")) {
            ps.setString(1, id);
            return ps.executeUpdate() > 0;
        } catch (Exception ex) {
            throw new IllegalStateException("memory delete failed: " + ex.getMessage(), ex);
        }
    }

    public void markHit(String id) {
        Instant now = Ids.now();
        if (!useSqlite) {
            findById(id).ifPresent(m -> {
                m.setHitCount(m.getHitCount() + 1);
                m.setLastHitAt(now);
            });
            return;
        }
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement(
                     "update memories set hit_count=hit_count+1, last_hit_at=? where id=?")) {
            ps.setString(1, now.toString());
            ps.setString(2, id);
            ps.executeUpdate();
        } catch (Exception ignored) {
        }
    }

    public void clearSession(String sessionId) {
        if (!useSqlite) {
            memoryFallback.removeIf(m -> sessionMatches(m, sessionId));
            return;
        }
        try (Connection c = conn();
             PreparedStatement ps = c.prepareStatement("delete from memories where session_id=?")) {
            ps.setString(1, sessionId == null ? "local" : sessionId);
            ps.executeUpdate();
        } catch (Exception ignored) {
        }
    }

    private static boolean sessionMatches(MemoryEntry m, String sessionId) {
        String sid = sessionId == null ? "local" : sessionId;
        return sid.equals(m.getSessionId());
    }

    private void bind(PreparedStatement ps, MemoryEntry e) throws Exception {
        ps.setString(1, e.getId());
        ps.setString(2, e.getSessionId());
        ps.setString(3, e.getCategory());
        ps.setString(4, e.getKey());
        ps.setString(5, e.getValue());
        ps.setString(6, e.getDomain());
        ps.setString(7, e.getSourceRunId());
        ps.setString(8, e.getCreatedAt().toString());
        ps.setDouble(9, e.getConfidence());
        ps.setInt(10, e.getHitCount());
        ps.setString(11, e.getLastHitAt() == null ? null : e.getLastHitAt().toString());
        ps.setInt(12, e.isActive() ? 1 : 0);
        ps.setString(13, e.getNote());
    }

    private MemoryEntry fromRs(ResultSet rs) throws Exception {
        MemoryEntry e = new MemoryEntry();
        e.setId(rs.getString("id"));
        e.setSessionId(rs.getString("session_id"));
        e.setCategory(rs.getString("category"));
        e.setKey(rs.getString("key"));
        e.setValue(rs.getString("value"));
        e.setDomain(rs.getString("domain"));
        e.setSourceRunId(rs.getString("source_run_id"));
        e.setCreatedAt(Instant.parse(rs.getString("created_at")));
        e.setConfidence(rs.getDouble("confidence"));
        e.setHitCount(rs.getInt("hit_count"));
        String lastHit = rs.getString("last_hit_at");
        if (lastHit != null) {
            e.setLastHitAt(Instant.parse(lastHit));
        }
        e.setActive(rs.getInt("active") == 1);
        e.setNote(rs.getString("note"));
        return e;
    }

    private Connection conn() throws Exception {
        return DriverManager.getConnection("jdbc:sqlite:" + dbPath.toAbsolutePath());
    }
}
