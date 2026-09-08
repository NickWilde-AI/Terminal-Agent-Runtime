package com.deviceagent.harness;

import com.deviceagent.model.CompiledTaskCandidate;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GoalCompilerCoverageTest {
    @Test
    void multiDomainRequestBindsAllIntents() {
        CompiledTaskCandidate c = GoalCompiler.compile(
                "打开空调，设为23度；左前车窗打开一半；播放周杰伦；然后导航到虹桥机场。",
                null,
                List.of()
        );
        assertEquals("AGENT", c.routeHint);
        assertTrue(c.goals.stream().anyMatch(g -> "climate_power".equals(g.get("type"))));
        assertTrue(c.goals.stream().anyMatch(g -> "cabin_temperature".equals(g.get("type")) && Integer.valueOf(23).equals(((Number) g.get("value")).intValue())));
        assertTrue(c.goals.stream().anyMatch(g -> "window_position".equals(g.get("type")) && "front_left".equals(g.get("window"))));
        assertTrue(c.goals.stream().anyMatch(g -> "media_play".equals(g.get("type")) && "周杰伦".equals(g.get("artist"))));
        assertTrue(c.goals.stream().anyMatch(g -> "nav_start".equals(g.get("type")) && "虹桥机场".equals(g.get("destination"))));
        assertTrue(c.raw.get("coverage_missing") == null);
    }

    @Test
    void restTaskKeepsNoWindowConstraint() {
        CompiledTaskCandidate c = GoalCompiler.compile(
                "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
                null,
                List.of()
        );
        assertEquals("AGENT", c.routeHint);
        assertTrue(c.constraints.stream().anyMatch(x -> "no_window".equals(x.get("type"))));
        assertTrue(c.goals.stream().noneMatch(g -> "window_position".equals(g.get("type"))));
    }
}
