"""Verify the complete HTTP draft path and persistence ordering without real saves."""
import unittest
from unittest.mock import Mock, patch
from oa_draft import create_draft


class HTTPDraftLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'employee': {'id':'1'}, 'public_project':'PUBLIC',
                     'application_reason':'归属调整', 'target_project':'PROJECT',
                     'adjustments':[{'date':'2026-09-21','hours':'4','target_project':'PROJECT'}]}
        self.client = Mock()
        self.client.identity.return_value = {'id':'1'}
        self.form = Mock()
        self.form.projects = {'PROJECT':{'id':'2'}}
        self.form.prepare.return_value = {'src':'save', 'requestid':'-1',
                                         'actiontype':'requestOperation','workflowid':'110092'}
        self.readback = Mock()

    def test_persists_id_before_readback_then_marks_verified(self):
        events = []
        def factory(client, request_id=None):
            events.append('readback' if request_id else 'initialize')
            return self.readback if request_id else self.form
        def send(client, request):
            self.assertIn('src=save', request['body'])
            events.append('send')
            return '123'
        def saved(result):
            events.append('verified' if result['verified'] else 'persist_id')
            self.assertFalse(result['oa_submitted'])
        with patch('oa_draft.OAForm',side_effect=factory), \
             patch('oa_draft.send_save_request',side_effect=send), \
             patch('oa_draft.verify_saved') as verify:
            result = create_draft(self.client,self.plan,lambda:events.append('before_save'),saved)
        self.assertEqual(events,['initialize','before_save','send','persist_id','readback','verified'])
        self.assertTrue(result['verified'])
        verify.assert_called_once()

    def test_preparation_failure_never_enters_save(self):
        self.form.prepare.side_effect = ValueError('联动失败')
        before, saved = Mock(), Mock()
        with patch('oa_draft.OAForm',return_value=self.form), patch('oa_draft.send_save_request') as send:
            with self.assertRaisesRegex(ValueError,'联动失败'):
                create_draft(self.client,self.plan,before,saved)
        before.assert_not_called(); saved.assert_not_called(); send.assert_not_called()

    def test_readback_failure_keeps_saved_id_without_second_save(self):
        persisted = []
        with patch('oa_draft.OAForm',side_effect=[self.form,self.readback]), \
             patch('oa_draft.send_save_request',return_value='123') as send, \
             patch('oa_draft.verify_saved',side_effect=ValueError('回读失败')):
            with self.assertRaisesRegex(ValueError,'回读失败'):
                create_draft(self.client,self.plan,Mock(),lambda result:persisted.append(dict(result)))
        send.assert_called_once()
        self.assertEqual(persisted[0]['request_id'],'123')
        self.assertFalse(persisted[0]['verified'])


if __name__ == '__main__': unittest.main()
