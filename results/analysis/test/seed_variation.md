# Seed variation (reported separately; seeds are never extra items)

> Stamp: frozen_test. Rows hold aggregates only; provenance: report.json#provenance (config 231365295e22).
> Intervals: 95% percentile, one shared dialogue bootstrap for every statistic of the run; slice intervals therefore differ from the per-run by_rule_level intervals, which resample only each slice's dialogues. Rates are seed-averaged per example before resampling. For a contrast, examples and dialogues give its smallest cell.

| system | line | endpoint | metric | n_seeds | mean | sd | min | max | per_seed |
|---|---|---|---|---|---|---|---|---|---|
| tfidf-utterance | test_time | stage1_correct | rate:none | 1 | 0.897 |  | 0.897 | 0.897 | 13=0.8970855231724797 |
| tfidf-utterance | test_time | stage1_correct | rate:one | 1 | 0.897 |  | 0.897 | 0.897 | 13=0.8970855231724797 |
| tfidf-utterance | test_time | stage1_correct | rate:full | 1 | 0.897 |  | 0.897 | 0.897 | 13=0.8970855231724797 |
| tfidf-utterance | test_time | stage1_correct | rate:mismatched | 1 | 0.897 |  | 0.897 | 0.897 | 13=0.897238525930915 |
| tfidf-utterance | test_time | stage1_correct | rate:mismatched_one | 1 | 0.897 |  | 0.897 | 0.897 | 13=0.897238525930915 |
| tfidf-utterance | test_time | stage1_correct | benefit:one_minus_none | 1 | 0.000 |  | 0.000 | 0.000 | 13=0.0 |
| tfidf-utterance | test_time | stage1_correct | benefit:full_minus_none | 1 | 0.000 |  | 0.000 | 0.000 | 13=0.0 |
| tfidf-utterance | test_time | stage1_correct | benefit:full_minus_one | 1 | 0.000 |  | 0.000 | 0.000 | 13=0.0 |
| tfidf-utterance | test_time | stage1_correct | primary_contrast:full_minus_none:linear | 1 | 0.000 |  | 0.000 | 0.000 | 13=0.0 |
| tfidf-context | test_time | stage1_correct | rate:none | 1 | 0.885 |  | 0.885 | 0.885 | 13=0.884854276158624 |
| tfidf-context | test_time | stage1_correct | rate:one | 1 | 0.891 |  | 0.891 | 0.891 | 13=0.8910654562828476 |
| tfidf-context | test_time | stage1_correct | rate:full | 1 | 0.895 |  | 0.895 | 0.895 | 13=0.8948877209746775 |
| tfidf-context | test_time | stage1_correct | rate:mismatched | 1 | 0.889 |  | 0.889 | 0.889 | 13=0.8893486000192438 |
| tfidf-context | test_time | stage1_correct | rate:mismatched_one | 1 | 0.885 |  | 0.885 | 0.885 | 13=0.8845376695852978 |
| tfidf-context | test_time | stage1_correct | benefit:one_minus_none | 1 | 0.006 |  | 0.006 | 0.006 | 13=0.006211180124223602 |
| tfidf-context | test_time | stage1_correct | benefit:full_minus_none | 1 | 0.010 |  | 0.010 | 0.010 | 13=0.010033444816053512 |
| tfidf-context | test_time | stage1_correct | benefit:full_minus_one | 1 | 0.004 |  | 0.004 | 0.004 | 13=0.003822264691829909 |
| tfidf-context | test_time | stage1_correct | primary_contrast:full_minus_none:linear | 1 | -0.010 |  | -0.010 | -0.010 | 13=-0.010340989159768034 |
| deberta-v3-base | matched | stage1_correct | rate:none | 5 | 0.924 | 0.001 | 0.923 | 0.926 | 13=0.9243191591017678; 42=0.9255613951266125; 314=0.9229813664596274; 2026=0.9227902532250358; 2718=0.9251791686574296 |
| deberta-v3-base | matched | stage1_correct | rate:one | 5 | 0.926 | 0.001 | 0.925 | 0.927 | 13=0.925752508361204; 42=0.926899187768753; 314=0.925370281892021; 2026=0.9245102723363593; 2718=0.9259436215957955 |
| deberta-v3-base | matched | stage1_correct | rate:full | 5 | 0.926 | 0.001 | 0.925 | 0.927 | 13=0.9267080745341615; 42=0.92651696129957; 314=0.9254658385093167; 2026=0.9263258480649785; 2718=0.9248924988055423 |
| deberta-v3-base | matched | stage1_correct | rate:mismatched | 5 | 0.911 | 0.003 | 0.908 | 0.915 | 13=0.9148465313191572; 42=0.9098431636678533; 314=0.9118637544501107; 2026=0.9083998845376696; 2718=0.9096507264504955 |
| deberta-v3-base | matched | stage1_correct | rate:mismatched_one | 5 | 0.910 | 0.003 | 0.907 | 0.915 | 13=0.9148465313191572; 42=0.910228038102569; 314=0.908977196189743; 2026=0.9073414798422015; 2718=0.9098431636678533 |
| deberta-v3-base | matched | stage1_correct | benefit:one_minus_none | 5 | 0.002 | 0.001 | 0.001 | 0.002 | 13=0.001433349259436216; 42=0.0013377926421404682; 314=0.0023889154323936935; 2026=0.001720019111323459; 2718=0.0007644529383659818 |
| deberta-v3-base | matched | stage1_correct | benefit:full_minus_none | 5 | 0.002 | 0.001 | -0.000 | 0.004 | 13=0.0023889154323936935; 42=0.0009555661729574773; 314=0.002484472049689441; 2026=0.003535594839942666; 2718=-0.0002866698518872432 |
| deberta-v3-base | matched | stage1_correct | benefit:full_minus_one | 5 | 0.000 | 0.001 | -0.001 | 0.002 | 13=0.0009555661729574773; 42=-0.0003822264691829909; 314=9.555661729574773e-05; 2026=0.001815575728619207; 2718=-0.001051122790253225 |
| deberta-v3-base | matched | stage1_correct | primary_contrast:full_minus_none:linear | 5 | 0.002 | 0.003 | -0.002 | 0.007 | 13=-0.0019784897601117643; 42=0.0018668714218753706; 314=0.004829864106497026; 2026=0.006696735528372397; 2718=0.0004675081813931744 |
| deberta-v3-large | matched | stage1_correct | rate:none | 5 | 0.927 | 0.001 | 0.926 | 0.928 | 13=0.9270903010033444; 42=0.9277591973244147; 314=0.9283325370281892; 2026=0.925752508361204; 2718=0.9266125179168657 |
| deberta-v3-large | matched | stage1_correct | rate:one | 5 | 0.930 | 0.001 | 0.929 | 0.931 | 13=0.9288103201146679; 42=0.9308170090778787; 314=0.9298614429049211; 2026=0.9308170090778787; 2718=0.9294792164357382 |
| deberta-v3-large | matched | stage1_correct | rate:full | 5 | 0.928 | 0.001 | 0.927 | 0.929 | 13=0.9282369804108934; 42=0.928428093645485; 314=0.9266125179168657; 2026=0.9288103201146679; 2718=0.9293836598184424 |
| deberta-v3-large | matched | stage1_correct | rate:mismatched | 5 | 0.903 | 0.001 | 0.901 | 0.905 | 13=0.903204079669008; 42=0.9050322332339075; 314=0.904358702973155; 2026=0.9029154238429712; 2718=0.9014721447127875 |
| deberta-v3-large | matched | stage1_correct | rate:mismatched_one | 5 | 0.905 | 0.001 | 0.903 | 0.906 | 13=0.9053208890599442; 42=0.9033965168863658; 314=0.9061868565380544; 2026=0.9054171076686232; 2718=0.9035889541037236 |
| deberta-v3-large | matched | stage1_correct | benefit:one_minus_none | 5 | 0.003 | 0.001 | 0.002 | 0.005 | 13=0.001720019111323459; 42=0.0030578117534639272; 314=0.0015289058767319636; 2026=0.00506450071667463; 2718=0.002866698518872432 |
| deberta-v3-large | matched | stage1_correct | benefit:full_minus_none | 5 | 0.001 | 0.002 | -0.002 | 0.003 | 13=0.0011466794075489727; 42=0.0006688963210702341; 314=-0.001720019111323459; 2026=0.0030578117534639272; 2718=0.0027711419015766844 |
| deberta-v3-large | matched | stage1_correct | benefit:full_minus_one | 5 | -0.002 | 0.001 | -0.003 | -0.000 | 13=-0.0005733397037744864; 42=-0.0023889154323936935; 314=-0.003248924988055423; 2026=-0.002006688963210702; 2718=-9.555661729574773e-05 |
| deberta-v3-large | matched | stage1_correct | primary_contrast:full_minus_none:linear | 5 | 0.003 | 0.004 | -0.001 | 0.007 | 13=0.007220052878883768; 42=-0.0002105914616834792; 314=-0.0013498766787586533; 2026=0.007325348609725508; 2718=0.0020743015798615223 |
| qwen2.5-7b-instruct | test_time | request_interpretation | rate:none | 1 | 0.179 |  | 0.179 | 0.179 | 0=0.17939160755079955 |
| qwen2.5-7b-instruct | test_time | request_interpretation | rate:one | 1 | 0.197 |  | 0.197 | 0.197 | 0=0.19742695683539738 |
| qwen2.5-7b-instruct | test_time | request_interpretation | rate:full | 1 | 0.186 |  | 0.186 | 0.186 | 0=0.18588433329325477 |
| qwen2.5-7b-instruct | test_time | request_interpretation | rate:mismatched | 1 | 0.127 |  | 0.127 | 0.127 | 0=0.12745926372963187 |
| qwen2.5-7b-instruct | test_time | request_interpretation | rate:mismatched_one | 1 | 0.148 |  | 0.148 | 0.148 | 0=0.14809897404948702 |
| qwen2.5-7b-instruct | test_time | request_interpretation | benefit:one_minus_none | 1 | 0.018 |  | 0.018 | 0.018 | 0=0.018035349284597813 |
| qwen2.5-7b-instruct | test_time | request_interpretation | benefit:full_minus_none | 1 | 0.006 |  | 0.006 | 0.006 | 0=0.006492725742455212 |
| qwen2.5-7b-instruct | test_time | request_interpretation | benefit:full_minus_one | 1 | -0.012 |  | -0.012 | -0.012 | 0=-0.0115426235421426 |
| qwen2.5-7b-instruct | test_time | type_exact | rate:none | 1 | 0.287 |  | 0.287 | 0.287 | 0=0.28708042459596445 |
| qwen2.5-7b-instruct | test_time | type_exact | rate:one | 1 | 0.293 |  | 0.293 | 0.293 | 0=0.2925313187338625 |
| qwen2.5-7b-instruct | test_time | type_exact | rate:full | 1 | 0.272 |  | 0.272 | 0.272 | 0=0.2721621880080329 |
| qwen2.5-7b-instruct | test_time | type_exact | rate:mismatched | 1 | 0.232 |  | 0.232 | 0.232 | 0=0.23235435724602793 |
| qwen2.5-7b-instruct | test_time | type_exact | rate:mismatched_one | 1 | 0.260 |  | 0.260 | 0.260 | 0=0.2599903707270101 |
| qwen2.5-7b-instruct | test_time | type_exact | benefit:one_minus_none | 1 | 0.005 |  | 0.005 | 0.005 | 0=0.005450894137898059 |
| qwen2.5-7b-instruct | test_time | type_exact | benefit:full_minus_none | 1 | -0.015 |  | -0.015 | -0.015 | 0=-0.01491823658793153 |
| qwen2.5-7b-instruct | test_time | type_exact | benefit:full_minus_one | 1 | -0.020 |  | -0.020 | -0.020 | 0=-0.020369130725829587 |
| qwen2.5-7b-instruct | test_time | stage1_correct | rate:none | 1 | 0.668 |  | 0.668 | 0.668 | 0=0.6677496416626851 |
| qwen2.5-7b-instruct | test_time | stage1_correct | rate:one | 1 | 0.678 |  | 0.678 | 0.678 | 0=0.6784519827998089 |
| qwen2.5-7b-instruct | test_time | stage1_correct | rate:full | 1 | 0.672 |  | 0.672 | 0.672 | 0=0.6716674629718108 |
| qwen2.5-7b-instruct | test_time | stage1_correct | rate:mismatched | 1 | 0.598 |  | 0.598 | 0.598 | 0=0.5976137785047628 |
| qwen2.5-7b-instruct | test_time | stage1_correct | rate:mismatched_one | 1 | 0.622 |  | 0.622 | 0.622 | 0=0.6223419609352449 |
| qwen2.5-7b-instruct | test_time | stage1_correct | benefit:one_minus_none | 1 | 0.011 |  | 0.011 | 0.011 | 0=0.010702341137123745 |
| qwen2.5-7b-instruct | test_time | stage1_correct | benefit:full_minus_none | 1 | 0.004 |  | 0.004 | 0.004 | 0=0.003917821309125657 |
| qwen2.5-7b-instruct | test_time | stage1_correct | benefit:full_minus_one | 1 | -0.007 |  | -0.007 | -0.007 | 0=-0.006784519827998089 |
| qwen2.5-7b-instruct | test_time | request_interpretation | primary_contrast:full_minus_none:linear | 1 | -0.006 |  | -0.006 | -0.006 | 0=-0.0061970235340288345 |
| hybrid | matched | request_interpretation | rate:none | 5 | 0.181 | 0.000 | 0.181 | 0.181 | 13=0.1808344354935674; 42=0.1809546711554647; 314=0.18107490681736202; 2026=0.18107490681736202; 2718=0.18107490681736202 |
| hybrid | matched | request_interpretation | rate:one | 5 | 0.200 | 0.000 | 0.200 | 0.200 | 13=0.19995190573524108; 42=0.19995190573524108; 314=0.20031261272093304; 2026=0.20031261272093304; 2718=0.19983167007334376 |
| hybrid | matched | request_interpretation | rate:full | 5 | 0.186 | 0.000 | 0.186 | 0.186 | 13=0.18576409763135746; 42=0.18588433329325477; 314=0.1860045689551521; 2026=0.18612480461704942; 2718=0.18576409763135746 |
| hybrid | matched | request_interpretation | rate:mismatched | 5 | 0.130 | 0.000 | 0.129 | 0.130 | 13=0.12963186481593242; 42=0.12939046469523235; 314=0.1295111647555824; 2026=0.12963186481593242; 2718=0.1295111647555824 |
| hybrid | matched | request_interpretation | rate:mismatched_one | 5 | 0.153 | 0.000 | 0.153 | 0.153 | 13=0.1531683765841883; 42=0.1528062764031382; 314=0.15292697646348824; 2026=0.1531683765841883; 2718=0.15292697646348824 |
| hybrid | matched | request_interpretation | benefit:one_minus_none | 5 | 0.019 | 0.000 | 0.019 | 0.019 | 13=0.019117470241673682; 42=0.01899723457977636; 314=0.019237705903571; 2026=0.019237705903571; 2718=0.018756763255981725 |
| hybrid | matched | request_interpretation | benefit:full_minus_none | 5 | 0.005 | 0.000 | 0.005 | 0.005 | 13=0.004929662137790069; 42=0.004929662137790069; 314=0.004929662137790069; 2026=0.005049897799687387; 2718=0.004689190813995431 |
| hybrid | matched | request_interpretation | benefit:full_minus_one | 5 | -0.014 | 0.000 | -0.014 | -0.014 | 13=-0.014187808103883611; 42=-0.014067572441986293; 314=-0.014308043765780931; 2026=-0.014187808103883611; 2718=-0.014067572441986293 |
| hybrid | matched | type_exact | rate:none | 5 | 0.329 | 0.001 | 0.329 | 0.330 | 13=0.3299225399254088; 42=0.33040068853399635; 314=0.3288706129865162; 2026=0.3285837238213637; 2718=0.3291575021516687 |
| hybrid | matched | type_exact | rate:one | 5 | 0.344 | 0.001 | 0.343 | 0.345 | 13=0.3426412929138376; 42=0.3444582576264703; 314=0.3431194415224252; 2026=0.3435019604092952; 2718=0.3447451467916228 |
| hybrid | matched | type_exact | rate:full | 5 | 0.333 | 0.001 | 0.332 | 0.334 | 13=0.3326958018552166; 42=0.33326958018552166; 314=0.33231328296834656; 2026=0.33336520990723917; 2718=0.3343215071244143 |
| hybrid | matched | type_exact | rate:mismatched | 5 | 0.282 | 0.000 | 0.282 | 0.283 | 13=0.282522869523351; 42=0.282522869523351; 314=0.28194511314395765; 2026=0.2821376986037554; 2718=0.2823302840635532 |
| hybrid | matched | type_exact | rate:mismatched_one | 5 | 0.299 | 0.001 | 0.298 | 0.300 | 13=0.29889263360616275; 42=0.29889263360616275; 314=0.29985556090515164; 2026=0.29889263360616275; 2718=0.2984111699566683 |
| hybrid | matched | type_exact | benefit:one_minus_none | 5 | 0.014 | 0.001 | 0.013 | 0.016 | 13=0.012718752988428804; 42=0.01405756909247394; 314=0.014248828535908961; 2026=0.01491823658793153; 2718=0.015587644639954098 |
| hybrid | matched | type_exact | benefit:full_minus_none | 5 | 0.004 | 0.001 | 0.003 | 0.005 | 13=0.002773261929807784; 42=0.002868891651525294; 314=0.003442669981830353; 2026=0.0047814860858754905; 2718=0.005164004972745529 |
| hybrid | matched | type_exact | benefit:full_minus_one | 5 | -0.011 | 0.001 | -0.011 | -0.010 | 13=-0.00994549105862102; 42=-0.011188677440948647; 314=-0.010806158554078607; 2026=-0.010136750502056039; 2718=-0.010423639667208568 |
| hybrid | matched | stage1_correct | rate:none | 5 | 0.921 | 0.001 | 0.919 | 0.922 | 13=0.9206880076445294; 42=0.9212613473483039; 314=0.9219302436693741; 2026=0.9193502150023889; 2718=0.9202102245580507 |
| hybrid | matched | stage1_correct | rate:one | 5 | 0.927 | 0.001 | 0.925 | 0.927 | 13=0.9254658385093167; 42=0.9274725274725275; 314=0.92651696129957; 2026=0.9274725274725275; 2718=0.926134734830387 |
| hybrid | matched | stage1_correct | rate:full | 5 | 0.926 | 0.001 | 0.924 | 0.927 | 13=0.925752508361204; 42=0.9260391782130912; 314=0.9241280458671763; 2026=0.9263258480649785; 2718=0.926899187768753 |
| hybrid | matched | stage1_correct | rate:mismatched | 5 | 0.892 | 0.001 | 0.890 | 0.893 | 13=0.891369190801501; 42=0.8931011257577215; 314=0.892620032714327; 2026=0.8910805349754642; 2718=0.8896372558452805 |
| hybrid | matched | stage1_correct | rate:mismatched_one | 5 | 0.895 | 0.001 | 0.894 | 0.897 | 13=0.8957952468007313; 42=0.8940633118445107; 314=0.8968536514961993; 2026=0.8958914654094102; 2718=0.8943519676705475 |
| hybrid | matched | stage1_correct | benefit:one_minus_none | 5 | 0.006 | 0.001 | 0.005 | 0.008 | 13=0.004777830864787387; 42=0.006211180124223602; 314=0.004586717630195891; 2026=0.008122312470138558; 2718=0.005924510272336359 |
| hybrid | matched | stage1_correct | benefit:full_minus_none | 5 | 0.005 | 0.002 | 0.002 | 0.007 | 13=0.00506450071667463; 42=0.004777830864787387; 314=0.002197802197802198; 2026=0.006975633062589585; 2718=0.006688963210702341 |
| hybrid | matched | stage1_correct | benefit:full_minus_one | 5 | -0.001 | 0.001 | -0.002 | 0.001 | 13=0.0002866698518872432; 42=-0.001433349259436216; 314=-0.0023889154323936935; 2026=-0.0011466794075489727; 2718=0.0007644529383659818 |
| hybrid | matched | request_interpretation | primary_contrast:full_minus_none:linear | 5 | -0.005 | 0.000 | -0.005 | -0.004 | 13=-0.004115316534289048; 42=-0.005311421345849878; 314=-0.005051207970882403; 2026=-0.005051207970882403; 2718=-0.004530781220947457 |
