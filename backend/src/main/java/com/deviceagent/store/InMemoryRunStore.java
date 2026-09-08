package com.deviceagent.store;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;
@Component
public class InMemoryRunStore {
    private final Map<String,RunRecord> runs=new ConcurrentHashMap<>();
    private final Map<String,String> requests=new ConcurrentHashMap<>();
    private final ObjectMapper mapper;private final Path dir;
    private Consumer<RunRecord> persistence=r->{};
    private final CopyOnWriteArrayList<Consumer<RuntimeEvent>> eventListeners=new CopyOnWriteArrayList<>();
    public InMemoryRunStore(ObjectMapper m,DeviceAgentProperties p)throws IOException{mapper=m;dir=Path.of(p.getEventLogDir());Files.createDirectories(dir);}
    public void onPersist(Consumer<RunRecord> sink){persistence=sink;}
    /** @deprecated prefer {@link #addEventListener(Consumer)} for multi-subscriber SSE */
    public void onEvent(Consumer<RuntimeEvent> sink){addEventListener(sink);}
    public void addEventListener(Consumer<RuntimeEvent> sink){eventListeners.add(sink);}
    public void removeEventListener(Consumer<RuntimeEvent> sink){eventListeners.remove(sink);}
    public Optional<RunRecord> findByRequestId(String id){return Optional.ofNullable(requests.get(id)).flatMap(this::find);}
    public Optional<RunRecord> find(String id){return Optional.ofNullable(runs.get(id));}
    public void save(RunRecord r){runs.put(r.getRunId(),r);if(r.getRequestId()!=null)requests.put(r.getRequestId(),r.getRunId());}
    public List<RunRecord> list(){return new ArrayList<>(runs.values());}
    public boolean hasActiveWriteRun(String device){return runs.values().stream().anyMatch(r->device.equals(r.getDeviceId())&&(!r.isTerminal()||r.isUnresolvedUnknown()));}
    public RuntimeEvent appendEvent(RunRecord r,String type,Map<String,Object> payload){
        RuntimeEvent e;
        synchronized(r){
            e=RuntimeEvent.of(type,payload);e.setRunId(r.getRunId());e.setEnvironmentId(r.getEnvironmentId());e.setGoalVersion(r.getTask().getGoalVersion());
            e.setSeq(r.getEvents().isEmpty()?1:r.getEvents().getLast().getSeq()+1);
            if(payload!=null&&payload.get("action_id")!=null)e.setActionId(payload.get("action_id").toString());
            r.getEvents().add(e);r.touch();
            // Storage failure is fatal to new dispatch; never silently claim replay durability.
            persistence.accept(r);
            try{Files.writeString(dir.resolve(r.getRunId()+".jsonl"),mapper.writeValueAsString(e)+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);}catch(IOException ex){throw new IllegalStateException("EVENT_STORAGE_UNAVAILABLE",ex);}
        }
        for(Consumer<RuntimeEvent> listener:eventListeners) listener.accept(e);
        return e;
    }
    public List<RuntimeEvent> eventsAfter(String id,long seq){return find(id).map(r->{synchronized(r){return r.getEvents().stream().filter(e->e.getSeq()>seq).toList();}}).orElse(List.of());}
}
