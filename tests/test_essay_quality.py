"""Structural contracts for recorded explanations; not a prose quality scorer."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import essay_hook
from validate_essay_checkpoint import validate
from test_essay_hook import pre_draft, draft_review, checkpoint


def brief():
    return {
        'direct_answer': '글 수정 시 반복하던 전체 배포 작업을 없앴다.',
        'context': '내용만 바뀌어도 전체 프로그램을 다시 배포해야 했다.',
        'judgment_action': '내용 갱신과 프로그램 배포를 분리했다.',
        'outcome': '글 수정은 내용만 갱신하면 반영됐다.',
    }


def plan_v2():
    plan = pre_draft()
    plan.update(schema_version=2, evidence_mapping_required=True)
    q = plan['questions'][0]
    q['writing_brief'] = brief()
    q['detail_selection'] = ['없어진 전체 배포 작업을 남기고 비교 기준 없는 실행 시간은 뺀다.']
    q['evidence_map'] = [{'subquestion': q['subquestions'][0],
                          'source': 'facts.md#F1', 'claim': brief()['outcome']}]
    return plan


def review_v2():
    review = draft_review()
    review['schema_version'] = 2
    q = review['questions'][0]
    q['reader_review'] = {'summary': brief(),
                          'question_fit': '이전의 불편과 직접 바꾼 구조, 없어진 작업으로 개선을 설명한다.',
                          'issues': []}
    q['answer_evidence'] = [{'source': 'facts.md#F1', 'quote': '내용 갱신과 프로그램 배포를 분리했습니다.'}]
    return review


class EssayQualityContractTest(unittest.TestCase):
    def test_v1_remains_readable_without_new_review(self):
        self.assertEqual(validate(pre_draft()), [])
        self.assertEqual(validate(draft_review()), [])

    def test_new_plan_requires_explanation_and_information_selection(self):
        for field in ('writing_brief', 'detail_selection'):
            with self.subTest(field=field):
                plan = plan_v2()
                del plan['questions'][0][field]
                self.assertTrue(any(field in error for error in validate(plan)))
        self.assertEqual(validate(plan_v2()), [])

    def test_experience_requires_context_action_and_outcome(self):
        for field in ('direct_answer', 'context', 'judgment_action', 'outcome'):
            with self.subTest(field=field):
                plan = plan_v2()
                plan['questions'][0]['writing_brief'][field] = ' '
                self.assertTrue(any(field in error for error in validate(plan)))
                review = review_v2()
                del review['questions'][0]['reader_review']['summary'][field]
                self.assertTrue(any(field in error for error in validate(review)))

    def test_personal_values_do_not_require_invented_experience(self):
        plan, review = plan_v2(), review_v2()
        p, q = plan['questions'][0], review['questions'][0]
        p.update(experience_question=False, question_type='직장 선택 기준',
                 subquestions=['선택 기준'], material_fit_reason='사용자가 확인한 선택 기준',
                 evidence_map=[{'subquestion':'선택 기준','source':'facts.md#F2','claim':'동료에게 피드백을 받을 수 있는 조직'}],
                 writing_brief={'direct_answer':'동료에게 피드백을 받을 수 있는 조직을 원한다.'})
        q['experience_question'] = False
        q['reader_review']['summary'] = {'direct_answer': '동료 피드백을 선택 기준으로 제시한다.'}
        q['reader_review']['question_fit'] = '직장 선택 기준을 직접 설명한다.'
        self.assertEqual(validate(plan), [])
        self.assertEqual(validate(review), [])

    def test_partial_plan_does_not_force_brief_for_missing_facts(self):
        plan = plan_v2()
        deferred = copy.deepcopy(plan['questions'][0])
        deferred.update(id='2', action='defer', material_fit='missing',
                        material_fit_reason='당시 추가 목표가 확인되지 않음',
                        missing_information=['당시 이미 가능한 수준과 추가 목표'],
                        follow_up_questions=['당시 이미 가능한 수준에서 무엇을 추가로 달성하려 했나요?'])
        del deferred['writing_brief']
        del deferred['detail_selection']
        plan['questions'].append(deferred)
        plan['document_status'] = 'ready_partial'
        self.assertEqual(validate(plan), [])

    def test_true_checkboxes_cannot_replace_reader_review(self):
        review = review_v2()
        del review['questions'][0]['reader_review']
        self.assertTrue(any('reader_review' in error for error in validate(review)))
        self.assertEqual(validate(review_v2()), [])

    def test_open_issue_and_unrecorded_resolution_block_valid(self):
        review = review_v2()
        issue = {'id': 'R1', 'quote': '갱신에 38초가 걸렸습니다.',
                 'problem': '이전 시간과 비교되지 않아 개선 효과를 알 수 없음',
                 'status': 'open'}
        review['questions'][0]['reader_review']['issues'] = [issue]
        self.assertTrue(any('미해결 독해' in error for error in validate(review)))
        issue['status'] = 'resolved'
        self.assertTrue(any('resolution' in error for error in validate(review)))
        issue['resolution'] = '시간을 빼고 없어졌던 반복 작업을 설명했다. 본문에서 전후 차이를 확인했다.'
        self.assertTrue(any('revision.issue_ids' in error for error in validate(review)))
        review['revision']['issue_ids'] = ['R1']
        review['revision']['resolved_issues'] = ['R1']
        self.assertEqual(validate(review), [])

    def test_malformed_review_is_rejected_without_crashing(self):
        for value in (None, [], True, {'summary': [], 'question_fit': True, 'issues': {}},
                      {'summary': brief(), 'question_fit': '근거', 'issues': [None]}):
            with self.subTest(value=value):
                review = review_v2()
                review['questions'][0]['reader_review'] = value
                self.assertTrue(validate(review))

    def test_v2_requires_evidence_even_if_toggle_is_removed(self):
        plan = plan_v2()
        del plan['evidence_mapping_required']
        self.assertTrue(any('evidence_mapping_required' in error for error in validate(plan)))
        review = review_v2()
        review['questions'][0]['answer_evidence'] = []
        self.assertTrue(any('answer_evidence' in error for error in validate(review)))

    def test_hook_rejects_review_downgrade_and_checks_actual_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan_path, draft_path = root/'plan.md', root/'draft.md'
            plan_path.write_text(checkpoint(plan_v2()), encoding='utf-8')
            body = '[전체 배포 작업 제거]\n내용 갱신과 프로그램 배포를 분리했습니다.'
            state = {'plan_file':'plan.md','draft_file':'draft.md',
                     'character_limits':[{'id':'1','min':0,'max':None}]}
            def check(review):
                draft_path.write_text('```text question=1\n'+body+'\n```\n'+checkpoint(review), encoding='utf-8')
                return essay_hook.validate_run(root, state)
            review = review_v2()
            self.assertTrue(check(review)['valid'])
            review['schema_version'] = 1
            self.assertTrue(any('schema_version' in error for error in check(review)['errors']))
            review['schema_version'] = 2
            review['questions'][0]['answer_evidence'][0]['quote'] = '본문에 없는 성과'
            self.assertTrue(any('인용 구절' in error for error in check(review)['errors']))

    def test_cli_rejects_missing_reader_record(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'draft.md'
            review = review_v2()
            del review['questions'][0]['reader_review']
            path.write_text(checkpoint(review), encoding='utf-8')
            result = subprocess.run([sys.executable,str(Path(essay_hook.__file__).with_name('validate_essay_checkpoint.py')),
                                     '--json',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(json.loads(result.stdout)['valid'])


if __name__ == '__main__':
    unittest.main()
