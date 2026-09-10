package com.deviceagent;

import com.deviceagent.eval.EvalRunner;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class FakeEvalGateTest {
    @Autowired
    EvalRunner evalRunner;

    @Test
    void fakeAgentEvalShouldPassAllSeeds() {
        Map<String, Object> report = evalRunner.run("agent");
        assertEquals("fake", report.get("model_mode"));
        assertEquals(54, report.get("total"));
        int failed = ((Number) report.get("failed")).intValue();
        if (failed > 0) {
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> cases = (List<Map<String, Object>>) report.get("cases");
            StringBuilder sb = new StringBuilder();
            for (Map<String, Object> c : cases) {
                if (!Boolean.TRUE.equals(c.get("passed"))) {
                    sb.append(c.get("id")).append(": ").append(c.get("message")).append('\n');
                }
            }
            assertEquals(0, failed, "Fake 评测门禁失败:\n" + sb);
        }
        assertEquals(0, ((Number) report.get("false_success")).intValue());
        assertTrue(((Number) report.get("passed")).intValue() >= 50);
    }
}
