# 웹사이트 결과 업데이트 준비

## 현재 상태

- 가져온 저장소: https://github.com/LeGenAI/entropymath_eval.git
- 기준 커밋: `6a024e9` (`Add Lean formal benchmark evaluator v8`).
- 로컬 작업 브랜치: `prepare/website-results-20260826`.
- 원본 실험 폴더는 저장소 옆의 `../baekjaehyun_tokyo_experiment_package_20260826/`에 그대로 보존한다.
- 이 저장소는 평가 코드다. 웹사이트는 별도로 가져온 `../EntropyMath/webpage/`에 있다. 웹앱 기준 커밋은 `6c8ec5a`이며 실행·연결 안내는 `../EntropyMath/RESULTS_UPDATE.md`를 참고한다.
- 아래 도구는 로컬 검증용 중간 JSON을 생성한다. 라이브 사이트의 확인된 업로드 형식이 아니며, 어떤 네트워크 요청이나 배포도 하지 않는다.

## 결과 검증 및 JSON 재생성

Python 3.12만 필요하다. 모델 평가를 다시 실행하거나 API 키를 설정할 필요가 없다.

```sh
cd /Users/baegjaehyeon/Desktop/entropymath-web/entropymath_eval
python3 scripts/prepare_website_results.py \
  --package ../baekjaehyun_tokyo_experiment_package_20260826 \
  --output outputs/website_update/prepared_results.json
python3 -m unittest discover -s tests -p 'test_prepare_website_results.py' -v
```

성공 시 11개 모델, 총 1,182회 실행이 검증된다. 모델별 모든 문항에 `run_idx=0,1,2`가 정확히 하나씩 있어야 하며, 누락·중복은 오류로 중단한다. 이 도구는 현재 패키지 구조에 한정되어 있다. 벤치마크·모델 수 또는 채점 형식이 바뀌면 도구도 갱신해야 한다.

생성 파일은 `.gitignore`에 추가한 `outputs/website_update/` 규칙으로 Git에서 제외된다. 재실행하면 해당 생성 JSON만 갱신한다. 원본 패키지 내부를 출력 경로로 지정하는 것은 차단한다.

## 반영할 데이터

| 평가 데이터 | 결과 위치 (원본 패키지 기준) | 모델 수 | 문항/모델 | 실행 수 |
|---|---|---:|---:|---:|
| `tokyo_math_hf_private` | `results/tokyo_private_dataset_7models/` | 7 | 30 | 630 |
| `csat_2026_math_en` (API) | `results/csat_2026_math/`의 Kimi, Solar, K-EXAONE 폴더 | 3 | 46 | 414 |
| `csat_2026_math_en` (수동) | `results/csat_2026_math/motif3_web_chat/` | 1 | 46 | 138 |

모델 ID `deprk58vp9q3z6g`는 패키지 보고서에서 `KT Mi:dm 2.0 Base Instruct`로 표시된다. Motif 3는 웹 채팅, 응답 수준 `중간`의 수동 평가이므로 API 실행과 구분한다.

## 집계 시 주의사항

- `accuracy_at_1`: 첫 실행(`run_idx=0`)의 정답 문항 수 / 전체 문항 수.
- `run_accuracy`: 세 번의 모든 실행에서 정답 실행 수 / 전체 실행 수.
- `pass_at_3`: 세 번 중 하나라도 정답인 문항 수 / 전체 문항 수.
- 모든 값은 0~1 비율이다. 오류/타임아웃도 실행 수에 포함하고 오답 처리한다. `solved`는 정답 여부가 아니라 답 추출 여부이므로 채점에 쓰지 않는다.
- API 결과는 이 패키지의 정수 답과 원문 선택지 기호를 비교한다. `3`을 `③`으로 임의 변환하지 않는다. Motif의 기존 수동 `correct` 값을 보존한다.
- Kimi K3의 기존 `csat_2026_math_en_summary.json`은 오류 4건을 제외한다. 그 파일의 `accuracy_at_1=95.65%`를 그대로 쓰면 안 된다. 오류 포함 첫 실행 정답률은 **43/46 = 93.48%**, 전체 실행 정답률은 **126/138 = 91.30%**, Pass@3는 **44/46 = 95.65%**다.
- 기존 `scripts/summarize_entropymath_results.py`는 `_error.json`을 건너뛰고 남은 첫 실행을 선택한다. 이 준비 작업에서는 기존 평가/집계 코드를 변경하지 않았다.
- 기존 `scripts/analyze_results.py`의 웹용 JSON은 `categories`, `sorted_pids`, `problem_stats`를 사용하며, `accuracy`는 첫 실행 정답률이 아닌 **전체 실행 정답률**이다. 해당 스크립트는 다른 컴퓨터의 절대 경로가 하드코딩되어 있어 이 패키지에 그대로 실행하지 않는다.

## 웹사이트 연결 상태

1. `../EntropyMath/webpage/scripts/import_experiment_results.py`가 이 검증 함수를 재사용해 실제 사이트 형식의 요약 JSON 두 개를 생성한다. 새 11개 모델 결과는 로컬 웹사이트에 연결했으며 실제 배포 계정/대상은 아직 확인하지 않았다.
2. 기존 `KOR_CSAT_26_KOR`는 **국어 언어 추론** 시험이다. 새 `csat_2026_math_en`은 **수학을 영어로 평가**한 것으로, 서로 다른 과목이며 점수를 합치지 않는다.
3. Tokyo는 private 데이터셋이다. 사용자 요청에 따라 웹 가져오기 도구의 `--include-details`로 문제·정답·저장된 모델 응답을 로컬 상세 화면에 연결했다. 외부 배포 전에는 공개 범위를 확인해야 한다. 이 평가 저장소의 중간 JSON에는 여전히 정답률/문항별 정답 개수만 포함하며 원문, 토큰/시간 정보, 인증 정보, 절대 경로는 포함하지 않는다.
4. 기존 결과는 그대로 보존했다. 새 두 데이터셋에는 요약과 1,182회 실행 상세가 있고, 모델/문제별 셀에서 Run 1–3을 볼 수 있다. 원본에 없는 풀이는 생성하지 않으며 API 오류와 수동 웹 대화의 차이를 표시한다.

로컬 웹사이트 연결은 완료했다. 최종 전달 대상은 공개 평가 저장소의 `prepare/website-results-20260826` 브랜치이며, 코드·테스트·문서만 포함한다. 원본 실험 패키지, `.env`, 실행 및 재시도 기록은 커밋하지 않는다. 문제·응답 상세 데이터는 비공개 `LeGenAI/EntropyMath` 웹 저장소에서 관리하며, main 병합이나 공개 배포는 이번 전달 범위에 포함하지 않는다.

## Kimi K3 오류 4건만 재시도

`scripts/retry_kimi_errors.py`는 PID/실행 번호 `(36,0)`, `(37,0)`, `(42,1)`, `(42,2)`만 대상으로 한다. 실행 번호는 0부터 시작한다. 원본 프롬프트 해시, 모델/샘플링 설정, 138회 실행의 완전성을 먼저 검증한다.

```sh
python3 scripts/retry_kimi_errors.py \
  --package ../baekjaehyun_tokyo_experiment_package_20260826 \
  --dotenv .env \
  --output outputs/website_update/kimi_k3_error_retry_20260826
```

- `.env`의 `OPENROUTER_API_KEY`를 메모리에서 읽고 키나 공급자 오류 본문은 출력하지 않는다.
- 같은 `moonshotai/kimi-k3`, temperature=0, top_p=1, max_tokens=8192, no-tools 프롬프트를 사용한다. 각 슬롯당 API 요청 한 번, 동시 요청 두 개, 요청당 600초 제한이며 SDK 자동 재시도는 꺼져 있다.
- 출력 폴더가 이미 있으면 요청 전에 중단한다. 원본 네 오류 파일을 `original_errors/`에 백업하고 전체 원본 파일의 해시를 전후 비교한다. 원본 패키지를 수정하지 않는다.
- 새 응답과 `retry_manifest.json`을 별도로 저장한다. 채점은 기존 엄격한 정수/선택지 비교를 사용한다. 정답이 나올 때까지 반복하는 방식이 아니다.
- 네 요청이 모두 종료된 경우 웹 가져오기 도구에 `--kimi-retry-dir <재시도 폴더>`를 전달할 수 있다. 원본 해시가 맞는 오류 슬롯 중 응답을 받은 것만 교체하고 분모는 138회로 유지한다. 재시도도 실패한 슬롯은 원래 오류로 남기며, 진행 중이거나 일부 요청이 생략된 재시도는 반영하지 않는다.

재시도 단위 테스트는 `python3 -m unittest discover -s tests -p 'test_retry_kimi_errors.py' -v`로 실행하며 실제 API를 호출하지 않는다.

### 남은 오류만 DeepInfra로 재시도

첫 재시도에서 PID 37/run 0 한 건을 복구했다. 다음 명령은 그 결과를 바이트 단위로 보존·재사용하고 남은 `(36,0)`, `(42,1)`, `(42,2)` 세 건에만 요청한다. 출력 폴더가 이미 존재하면 중단하므로 완료된 배치를 다시 실행하지 않는다.

```sh
python3 scripts/retry_kimi_errors.py \
  --package ../baekjaehyun_tokyo_experiment_package_20260826 \
  --dotenv .env \
  --previous-retry-dir outputs/website_update/kimi_k3_error_retry_20260826 \
  --provider deepinfra/bf16 \
  --output outputs/website_update/kimi_k3_deepinfra_retry_20260826
```

OpenRouter의 `provider.only=["deepinfra/bf16"]`, `allow_fallbacks=false`, `require_parameters=true`를 사용하고 실제 응답 제공자가 `DeepInfra`인지 검증한다. 모델·프롬프트·8192 토큰 한도와 600초 제한은 그대로다. 성공 여부와 관계없이 응답 ID, 제공자, 종료 사유 및 보고된 토큰 사용량을 진단 기록에 남긴다. 이전 보고서는 `previous_retry_manifest.json`으로 보존하며 `request_count`는 이번 API 요청 수, `reused_count`는 재요청하지 않은 성공 결과 수다. 웹 가져오기 도구에는 최신 재시도 폴더를 전달한다.
