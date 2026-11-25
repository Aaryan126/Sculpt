import io
import itertools
import json
import unittest
from unittest.mock import patch

import tailor


class Response(io.BytesIO):
    def __init__(self, body, content_type='text/event-stream'):
        super().__init__(body)
        self.headers={'Content-Type':content_type}


def event(delta=None, finish=None):
    return ('data: '+json.dumps({'choices':[{'index':0,'delta':delta or {},'finish_reason':finish}]})+'\n\n').encode()


class StreamingTests(unittest.TestCase):
    def test_active_stream_can_run_over_five_minutes_without_exposing_reasoning(self):
        body=(event({'reasoning':'Private model reasoning must stay out of logs.'})+
              event({'content':'{"ok":'})+event({'content':'true}'})+event(finish='stop')+b'data: [DONE]\n\n')
        config={'SOCLAAS_BASE_URL':'https://example.test/v1','SOCLAAS_API_KEY':'test-secret',
                'SOCLAAS_MODEL':'test-model','SOCLAAS_TIMEOUT_SECONDS':'30'}
        clock=itertools.count(0,60)
        progress=[]
        logs=io.StringIO()
        with patch.object(tailor,'load_env',return_value=config), \
             patch.object(tailor.urllib.request,'urlopen',return_value=Response(body)) as request, \
             patch.object(tailor,'_ssl_context',return_value=object()), \
             patch.object(tailor.time,'monotonic',side_effect=lambda:next(clock)), \
             patch('sys.stderr',logs):
            result=tailor._request_json([{'role':'user','content':'JSON please'}],progress=progress.append)
        self.assertEqual(result,{'ok':True})
        self.assertGreater(max(progress),300)
        self.assertEqual(request.call_args.kwargs['timeout'],30,'Timeout is socket inactivity, not total elapsed time')
        self.assertTrue(json.loads(request.call_args.args[0].data)['stream'])
        self.assertNotIn('Private model reasoning',logs.getvalue())
        self.assertNotIn('test-secret',logs.getvalue())

    def test_truncated_stream_is_not_accepted_even_if_partial_json_is_valid(self):
        body=event({'content':'{"ok":true}'})
        with self.assertRaisesRegex(tailor.AIServiceError,'disconnected'):
            tailor._read_event_stream(Response(body),'test',None,0)

    def test_length_limit_and_provider_stream_error_are_retryable(self):
        for body in [event({'content':'{"ok":true}'},'length'),
                     b'data: {"error":{"message":"provider failure"}}\n\n',
                     b'data: not-json\n\n']:
            with self.assertRaises(tailor.AIServiceError):
                tailor._read_event_stream(Response(body),'test',None,0)

    def test_json_provider_fallback(self):
        config={'SOCLAAS_BASE_URL':'https://example.test/v1','SOCLAAS_API_KEY':'test-secret','SOCLAAS_MODEL':'test'}
        body=json.dumps({'choices':[{'message':{'content':'{"ok":true}'}}]}).encode()
        with patch.object(tailor,'load_env',return_value=config), \
             patch.object(tailor.urllib.request,'urlopen',return_value=Response(body,'application/json')), \
             patch.object(tailor,'_ssl_context',return_value=object()):
            self.assertEqual(tailor._request_json([]),{'ok':True})


if __name__=='__main__': unittest.main()
