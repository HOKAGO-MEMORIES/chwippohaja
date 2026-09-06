from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import application_state as aps
import application_workspace as aw
import essay_hook as eh
import research_hook as rh
import workspace_setup as ws
from count_essay_characters import measure
from essay_rules import check_answers, validate_rules
from validate_essay_checkpoint import load_checkpoint, validate
from validate_essay_style import analyze
from validate_research_stage import validate_research_stage
from test_essay_hook import checkpoint, pre_draft, draft_review
import test_validate_research_stage as research_fixture


class WorkflowRegressions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = (Path(self.temporary.name) / '취업').resolve()
        ws.apply_setup(self.root, 'local', '시즌', 'disabled', 'disabled', False)
        self.app = Path(aw.apply_application(self.root, '예시전자', '백엔드')['application'])
        self.plan = self.app / '02_작성중/01_설계.md'
        self.draft = self.app / '02_작성중/02_답변.md'
        self.plan.write_text(checkpoint(pre_draft()), encoding='utf-8')
        self.body = '[고객의 수요]\n문제를 확인하고 구조를 바꾼 뒤 결과를 검증했습니다.'
        self.write_draft()

    def write_draft(self, body=None, review=None, path=None):
        (path or self.draft).write_text('```text question=1\n' + (body or self.body) + '\n```\n' + checkpoint(review or draft_review()), encoding='utf-8')

    def run_essay(self, command, *extra):
        args = eh.parse_args([command, '--workspace', str(self.root), *map(str, extra)])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = args.handler(args)
        return code, json.loads(output.getvalue())

    def start(self, *extra):
        self.run_essay('start', '--plan', self.plan, '--draft', self.draft, '--limit', '1:0:1500', *extra)
        return self.run_essay('plan-check')

    def test_registered_missing_question_blocks_plan_and_draft(self):
        code, result = self.start('--limit', '2:0:1500')
        self.assertEqual(code, 2)
        self.assertFalse(result['valid'])
        self.assertFalse(eh.validate_run(self.root, eh.load_state(self.root))['valid'])

    def test_malformed_checkpoint_blocks_with_validation_result(self):
        self.start()
        broken = pre_draft()
        broken['questions'] = None
        self.plan.write_text(checkpoint(broken), encoding='utf-8')
        code, result = self.run_essay('check')
        self.assertEqual(code, 2)
        self.assertFalse(result['valid'])

    def test_forbidden_summary_and_required_list_follow_employer_rules(self):
        rules = self.root/'rules.json'
        rules.write_text(json.dumps({'1': {'summary':'forbidden','body':'list','source':'기업의 공식 문항 안내'}}), encoding='utf-8')
        self.write_draft('- 요구사항을 확인했습니다.\n- 동료와 결과를 검증했습니다.')
        self.start('--rules', rules)
        self.assertEqual(self.run_essay('check')[0], 0)
        self.write_draft('[요약]\n- 요구사항을 확인했습니다.')
        self.assertEqual(self.run_essay('check')[0], 2)

    def test_rule_change_without_source_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_rules({'1': {'summary':'forbidden'}}, ['1'])
        with self.assertRaises(ValueError):
            validate_rules({'2': {'summary':'required'}}, ['1'])

    def test_nominal_noun_ending_in_yo_is_not_blocked(self):
        self.assertTrue(analyze('[고객의 수요]\n본문입니다.', plain=True)['structural_valid'])
        self.assertFalse(analyze('[수요를 확인했습니다]\n본문입니다.', plain=True)['structural_valid'])

    def test_tagged_blocks_bind_limits_by_id_even_when_reordered(self):
        q1 = draft_review()['questions'][0]
        q2 = copy.deepcopy(q1)
        q2['id'] = '2'
        source = '```text question=2\n[수요]\n길이가 긴 답변 본문입니다.\n```\n```text question=1\n[요약]\n짧음\n```'
        result = check_answers(source, [q1,q2], [{'id':'1','min':0,'max':9},{'id':'2','min':10,'max':100}], {})
        self.assertFalse(result['errors'])
        duplicate = source.replace('question=2','question=1')
        self.assertTrue(check_answers(duplicate,[q1,q2],[{'id':'1','min':0,'max':100},{'id':'2','min':0,'max':100}],{})['errors'])

    def test_counting_handles_korean_astral_unicode_spaces_and_newlines(self):
        text = '가 😀\n나'
        self.assertEqual(measure(text), 5)
        self.assertEqual(measure(text, 'utf16_units'), 6)
        self.assertEqual(measure(text, 'utf8_bytes'), 12)
        self.assertEqual(measure(text, whitespace='exclude'), 3)
        self.assertEqual(measure(text, line_endings='crlf'), 6)
        self.assertEqual(measure(text, line_endings='remove'), 4)

    def test_hook_enforces_byte_limit_instead_of_character_limit(self):
        rules = self.root/'rules.json'
        rules.write_text(json.dumps({'1': {'summary':'forbidden','unit':'utf8_bytes','source':'공식 안내: UTF-8 바이트'}}), encoding='utf-8')
        self.write_draft('가나다')
        self.run_essay('start','--plan',self.plan,'--draft',self.draft,'--limit','1:0:8','--rules',rules)
        self.run_essay('plan-check')
        self.assertEqual(self.run_essay('check')[0], 2)
        self.write_draft('가나')
        self.assertEqual(self.run_essay('check')[0], 0)

    def test_start_cannot_replace_other_application_or_reset_same_run(self):
        self.start()
        self.run_essay('wait','--reason','추가 사용자 경험을 확인해야 합니다.','--question','어떤 결과였나요?')
        before = eh.state_path(self.root).read_bytes()
        self.run_essay('start','--plan',self.plan,'--draft',self.draft,'--limit','1:0:1500')
        self.assertEqual(eh.state_path(self.root).read_bytes(), before)
        with self.assertRaises(ValueError):
            self.run_essay('start','--plan','시즌/회사B/02_작성중/설계.md','--draft','시즌/회사B/02_작성중/답변.md','--limit','1:0:1500')
        self.assertEqual(eh.state_path(self.root).read_bytes(), before)

    def test_suspend_other_application_then_resume_preserves_plan_and_rebinds(self):
        self.start()
        state = eh.load_state(self.root)
        state['session_id'] = 'old-session'
        eh.write_json_atomic(eh.state_path(self.root), state)
        _, suspended = self.run_essay('suspend')
        self.run_essay('start','--plan','시즌/회사B/02_작성중/설계.md','--draft','시즌/회사B/02_작성중/답변.md','--limit','1:0:1500')
        self.run_essay('suspend')
        self.run_essay('resume','--run-id',suspended['run_id'],'--rebind')
        restored=eh.load_state(self.root)
        self.assertEqual(restored['validated_plan_digest'], state['validated_plan_digest'])
        self.assertIsNone(restored['session_id'])
        self.assertEqual(self.run_essay('check')[0], 0)

    def test_advance_preserves_old_run_and_requires_new_plan_validation(self):
        self.start()
        previous=eh.load_state(self.root)
        next_draft=self.draft.with_name('03_답변.md')
        self.write_draft(path=next_draft)
        self.run_essay('advance','--plan',self.plan,'--draft',next_draft,'--limit','1:0:1500')
        self.assertTrue((self.root/eh.STATE.parent/'essay-history'/f"{previous['run_id']}.json").is_file())
        self.assertEqual(self.run_essay('check')[0],2)
        self.run_essay('plan-check')
        self.assertEqual(self.run_essay('finish')[0],0)
        self.assertTrue(self.draft.is_file())

    def test_current_research_ignores_preserved_old_incomplete_analysis(self):
        research_fixture.ValidateResearchStageTest().write_valid_documents(self.app)
        self.assertEqual(validate_research_stage(self.app)['status'],'complete')
        (self.app/'01_공고_JD/old_공고분석.md').write_text('# 이전 공고\n당시 접근 제한', encoding='utf-8')
        self.assertEqual(validate_research_stage(self.app)['status'],'partial')
        aps.select(self.app,'posting_analysis','01_공고_JD/예시전자_백엔드_공고분석.md','공식 공고 재확인 후 최신 분석 선택')
        self.assertEqual(validate_research_stage(self.app)['status'],'complete')

    def test_modified_selected_file_requires_explicit_reverification(self):
        research_fixture.ValidateResearchStageTest().write_valid_documents(self.app)
        path=self.app/'01_공고_JD/예시전자_백엔드_공고분석.md'
        aps.select(self.app,'posting_analysis',str(path),'현재 분석')
        path.write_text(path.read_text(encoding='utf-8')+'\n수정 사항',encoding='utf-8')
        self.assertEqual(validate_research_stage(self.app)['status'],'partial')
        aps.select(self.app,'posting_analysis',str(path),'수정 사항 재검증 완료')
        self.assertEqual(validate_research_stage(self.app)['status'],'complete')

    def test_older_adopted_draft_is_preserved_separately_from_submission(self):
        next_draft=self.draft.with_name('03_답변.md')
        self.write_draft(path=next_draft)
        aps.select(self.app,'essay',str(next_draft),'사용자 채택')
        aps.stage(self.app,'writing','valid_draft','문항과 사실 검사 통과')
        aps.stage(self.app,'submission','confirmed','사용자가 공식 제출 완료를 확인함')
        aps.select(self.app,'essay',str(self.draft),'사용자가 이전 버전을 다시 채택')
        state=aps.status_view(self.app)
        self.assertEqual(aps.current(self.app,'essay'),self.draft)
        self.assertNotIn('writing',state['stages'])
        self.assertEqual(state['stages']['submission']['status'],'confirmed')
        self.assertEqual(len(state['history']),4)

    def test_local_research_and_external_sync_recovery_are_independent(self):
        research_fixture.ValidateResearchStageTest().write_valid_documents(self.app)
        target={'application':self.app.relative_to(self.root).as_posix(),'disposition':None}
        state={'targets':[target],'required_services':['notion']}
        result=rh.validate_targets(self.root,state)
        self.assertTrue(result['targets'][0]['local_complete'])
        self.assertFalse(result['complete'])
        aps.sync(self.app,'notion','pending','권한이 부족하여 반영하지 못함')
        target['disposition']='partial'
        self.assertEqual(rh.validate_targets(self.root,state)['counts']['partial'],1)
        aps.sync(self.app,'notion','verified','페이지 재조회로 현재 링크와 속성 확인')
        self.assertFalse(rh.validate_targets(self.root,state)['complete'])
        target['disposition']=None
        self.assertTrue(rh.validate_targets(self.root,state)['complete'])
        path=self.app/'01_공고_JD/예시전자_기업리서치.md'
        path.write_text(path.read_text(encoding='utf-8')+'\n새 조사',encoding='utf-8')
        self.assertFalse(rh.validate_targets(self.root,state)['complete'])

    def test_evidence_map_requires_all_subquestions_and_real_answer_excerpt(self):
        plan=pre_draft()
        plan['evidence_mapping_required']=True
        self.assertTrue(validate(plan))
        question=plan['questions'][0]
        question['evidence_map']=[{'subquestion':question['subquestions'][0], 'source':'공통자료/사례.md#F1', 'claim':'구조 변경과 결과 검증'}]
        self.assertFalse(validate(plan))
        self.plan.write_text(checkpoint(plan),encoding='utf-8')
        self.start()
        self.assertEqual(self.run_essay('check')[0],2)
        review=draft_review()
        review['questions'][0]['answer_evidence']=[{'source':'공통자료/사례.md#F1','quote':'문제를 확인하고 구조를 바꾼 뒤 결과를 검증했습니다.'}]
        self.write_draft(review=review)
        self.assertEqual(self.run_essay('check')[0],0)
        review['questions'][0]['answer_evidence'][0]['quote']='본문에 없는 말'
        self.write_draft(review=review)
        self.assertEqual(self.run_essay('check')[0],2)

    def test_skill_templates_support_partial_then_complete_adopted_draft(self):
        self.body='[전체 배포 작업 제거]\n글만 바뀌어도 전체 프로그램을 배포해야 했습니다. 문제를 확인하고 구조를 바꾼 뒤 결과를 검증했습니다. 내용 갱신과 프로그램 배포를 분리해 글 수정에 전체 배포가 필요 없어졌습니다.'
        templates=Path(__file__).resolve().parents[1]/'assets/templates'
        plan_source=(templates/'자소서_작성설계.md').read_text(encoding='utf-8')
        draft_source=(templates/'자소서_작성본.md').read_text(encoding='utf-8')
        self.assertFalse((self.root/'작성템플릿').exists())
        profile=(self.root/'공통자료/경력_프로젝트_소재.md').read_text(encoding='utf-8')
        self.assertNotIn('- 연락처:',profile)
        self.assertNotIn('- 이메일:',profile)
        plan=load_checkpoint(plan_source)
        review=load_checkpoint(draft_source)
        self.assertTrue(validate(plan))
        self.assertTrue(validate(review))
        plan['document_status']='ready_partial'
        q1=plan['questions'][0]
        q1.update(pre_draft()['questions'][0])
        from test_essay_quality import brief
        q1['writing_brief']=brief()
        q1['detail_selection']=['문제와 변경 결과를 남기고 불필요한 구현 상세를 덜어냄']
        q1['evidence_map']=[{'subquestion':q1['subquestions'][0], 'source':'공통자료/사례.md#F1', 'claim':'문제 판단과 구조 개선 및 검증'}]
        q2=copy.deepcopy(q1)
        q2.update({'id':'2','question_type':'소통','subquestions':['어떻게 의견을 조율했는가'],
                   'action':'defer','material_fit':'missing','material_fit_reason':'확인된 소통 경험이 없음',
                   'evidence':[],'evidence_map':[], 'missing_information':['실제 의견 조율 경험'],
                   'follow_up_questions':['다른 의견을 어떻게 조율했나요?']})
        plan['questions'].append(q2)
        review.update(draft_review())
        review['schema_version']=2
        review['questions'][0]['reader_review']={'summary':brief(),'question_fit':'문제 판단과 구조 변경 및 결과를 설명함','issues':[]}
        review['document_status']='partial_draft'
        review['questions'][0]['answer_evidence']=[{'source':'공통자료/사례.md#F1','quote':'문제를 확인하고 구조를 바꾼 뒤 결과를 검증했습니다.'}]
        deferred={'id':'2','answer_status':'deferred','answer_present':False,
                  'experience_question':True,'reflection_required':False,'fatal_issues':[],
                  'recommended_issues':[],'missing_information':q2['missing_information'],
                  'follow_up_questions':q2['follow_up_questions']}
        review['questions'].append(deferred)
        from validate_essay_checkpoint import CHECKPOINT
        self.plan.write_text(CHECKPOINT.sub(lambda _:checkpoint(plan),plan_source),encoding='utf-8')
        self.draft.write_text(CHECKPOINT.sub(lambda _:checkpoint(review),draft_source)+'\n```text question=1\n'+self.body+'\n```\n',encoding='utf-8')
        self.start('--limit','2:0:1500')
        self.assertEqual(self.run_essay('check')[0],0)
        self.run_essay('wait','--reason','문항 2의 실제 소통 경험이 필요합니다.','--question','다른 의견을 어떻게 조율했나요?')
        original=self.draft.read_bytes()
        self.run_essay('resume')
        plan['document_status']='ready_full'
        q2.update({'action':'write','material_fit':'direct','material_fit_reason':'사용자가 대화와 합의 행동을 확인함',
                   'evidence':['사용자가 확인한 조율 사례'], 'missing_information':[], 'follow_up_questions':[],
                   'evidence_map':[{'subquestion':q2['subquestions'][0],'source':'공통자료/사례.md#F2','claim':'각자의 기준을 확인하고 합의안을 검증함'}]})
        q2['writing_brief']={'direct_answer':'서로의 기준을 확인해 합의안을 함께 검증했다.',
                             'context':'팀원마다 합의 기준이 달랐다.',
                             'judgment_action':'각자의 기준을 묻고 합의안을 함께 확인했다.',
                             'outcome':'같은 기준으로 합의안을 검증할 수 있었다.'}
        next_plan=self.plan.with_name('03_설계.md')
        next_draft=self.draft.with_name('04_답변.md')
        next_plan.write_text(checkpoint(plan),encoding='utf-8')
        review['document_status']='valid_draft'
        q2_review=copy.deepcopy(review['questions'][0])
        q2_review['id']='2'
        q2_review['reader_review']={'summary':copy.deepcopy(q2['writing_brief']),
                                    'question_fit':'기준의 차이와 확인 행동, 공동 검증 결과를 설명함','issues':[]}
        q2_review['answer_evidence']=[{'source':'공통자료/사례.md#F2','quote':'서로의 기준을 확인하고 합의안을 함께 검증했습니다.'}]
        review['questions'][1]=q2_review
        review['revision']['previous_version']=self.draft.name
        self.run_essay('advance','--plan',next_plan,'--draft',next_draft,'--limit','1:0:1500','--limit','2:0:1500')
        self.run_essay('plan-check')
        next_draft.write_text('```text question=1\n'+self.body+'\n```\n```text question=2\n[합의 기준의 확인]\n팀원마다 기준이 달랐습니다. 서로의 기준을 확인하고 합의안을 함께 검증했습니다. 같은 기준으로 결과를 확인할 수 있었습니다.\n```\n'+checkpoint(review),encoding='utf-8')
        self.assertEqual(self.run_essay('finish')[0],0)
        self.assertEqual(self.draft.read_bytes(),original)
        aps.select(self.app,'essay',str(next_draft),'사용자가 완성본 채택')
        aps.stage(self.app,'writing','valid_draft','전체 문항 검토와 훅 검사 통과')
        self.assertEqual(aps.status_view(self.app)['stages']['writing']['effective_status'],'valid_draft')

    def test_style_cli_uses_same_employer_rules_as_hook(self):
        import subprocess
        rules=self.root/'rules.json'
        rules.write_text(json.dumps({'1':{'summary':'forbidden','body':'list','source':'공식 요구'}}),encoding='utf-8')
        self.write_draft('- 요구사항을 확인했습니다.')
        completed=subprocess.run([sys.executable,str(Path(eh.__file__).with_name('validate_essay_style.py')),
                                  '--strict','--rules',str(rules),str(self.draft)],capture_output=True,encoding='utf-8')
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertTrue(json.loads(completed.stdout)['structural_valid'])


if __name__ == '__main__':
    unittest.main()
