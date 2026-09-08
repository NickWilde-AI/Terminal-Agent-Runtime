package com.deviceagent.model;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class CompiledTaskCandidate {
    public String routeHint; // FAST | AGENT | CLARIFY | REJECT
    public String clarifyQuestion;
    public String rejectReason;
    public List<Map<String, Object>> goals = new ArrayList<>();
    public List<Map<String, Object>> constraints = new ArrayList<>();
    public List<Map<String, Object>> criteria = new ArrayList<>();
    public Map<String, Object> fastAction; // capability_id + params
    public String summary;
    public Map<String, Object> raw = new LinkedHashMap<>();
}
