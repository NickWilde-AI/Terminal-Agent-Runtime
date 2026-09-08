package com.deviceagent.simulator;
import org.springframework.stereotype.Component;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.*;
@Component
public class SimulatorBean extends DeviceSimulator {
    private final ScheduledExecutorService clock=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"simulator-clock");t.setDaemon(true);return t;});
    @PostConstruct void start(){clock.scheduleWithFixedDelay(this::tick,100,50,TimeUnit.MILLISECONDS);}
    @PreDestroy void stop(){clock.shutdownNow();}
}
