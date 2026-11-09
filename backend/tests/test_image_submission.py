import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.image_retrieval.api import create_app
from src.image_retrieval.catalog import Catalog
from src.image_retrieval.config import Config
from src.image_retrieval.dres import load_dres_config
from src.image_retrieval.dres_submission import configured_media_name


def response(code=200, data=None):
    return Mock(status_code=code, json=Mock(return_value=data))


class ImageSubmissionTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        root = Path(folder)
        (root/'data/Batch1').mkdir(parents=True)
        Image.new('RGB', (128,72), 'red').save(root/'data/Batch1/08_1115.jpg')
        self.client = self.enterContext(TestClient(create_app(Config(data_root=root/'data', index_root=root/'index'))))
        self.factory = self.enterContext(patch('src.image_retrieval.dres_submission.requests.Session'))
        self.remote = self.factory.return_value.__enter__.return_value
        self.settings = self.enterContext(patch('src.image_retrieval.dres_submission.load_dres_config', return_value={
            'base_url':'https://dres.2hbread.com', 'metadata_mode':'admin'}))
        self.body = {'session_id':'secret-session', 'evaluation_id':'run', 'task':'kis',
                     'items':[{'image_id':'Batch1/08_1115.jpg', 'video_id':'Batch1/08', 'frame_id':1115, 'timestamp':999}],
                     'request_id':'request-1'}
        self.collection = {'id':'collection', 'name':'competition-images'}
        self.remote_image = {'name':'08_1115', 'type':'IMAGE', 'mediaItemId':'remote-image'}
        self.remote.post.return_value = response(data={'status':True, 'submission':'CORRECT', 'description':'Correct'})
        self.prepare()

    def prepare(self, status='ACTIVE', images=None):
        self.remote.get.side_effect = [response(data=[{'id':'run','status':status,'name':'Test'}]),
                                      response(data={'name':'KIS01','taskType':'KIS'}),
                                      response(data=[self.collection]),
                                      response(data=images if images is not None else [self.remote_image])]

    def test_preview_resolves_actual_media_name_without_submitting(self):
        result = self.client.post('/api/dres/submit/preview',json=self.body)
        self.assertEqual(result.status_code,200,result.text)
        data=result.json()
        self.assertTrue(data['dry_run'])
        self.assertEqual(data['payload'],{'answerSets':[{'taskName':'KIS01','answers':[{'mediaItemName':'08_1115','mediaItemCollectionName':'competition-images'}]}]})
        self.assertNotIn('secret-session',result.text)
        self.remote.post.assert_not_called()
        self.remote.cookies.set.assert_called_once_with('SESSIONID','secret-session',domain='dres.2hbread.com',path='/',secure=True)

    def test_submit_is_item_only_and_same_request_id_is_not_posted_twice(self):
        result=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'correct')
        answer=self.remote.post.call_args.kwargs['json']['answerSets'][0]['answers'][0]
        self.assertNotIn('start',answer)
        self.assertNotIn('end',answer)
        self.assertNotIn('video_id',answer)
        self.assertEqual(answer['mediaItemName'],'08_1115')
        self.assertEqual(self.remote.post.call_args.kwargs['params'],{'session':'secret-session'})
        again=self.client.post('/api/dres/submit',json=self.body)
        self.assertTrue(again.json()['replayed'])
        self.assertEqual(self.remote.post.call_count,1)

    def test_missing_ambiguous_and_non_image_items_never_submit(self):
        for values in [[],[self.remote_image,self.remote_image],[{**self.remote_image,'type':'VIDEO'}]]:
            self.prepare(images=values)
            result=self.client.post('/api/dres/submit',json=self.body)
            self.assertEqual(result.status_code,409,result.text)
        self.remote.post.assert_not_called()

    def test_finished_run_unknown_local_image_and_multiple_items_never_submit(self):
        self.prepare(status='FINISHED')
        self.assertEqual(self.client.post('/api/dres/submit',json=self.body).status_code,409)
        bad={**self.body,'items':[{'image_id':'Batch1/not-there.jpg'}]}
        self.assertEqual(self.client.post('/api/dres/submit',json=bad).status_code,404)
        self.assertEqual(self.client.post('/api/dres/submit',json={**self.body,'items':self.body['items']*2}).status_code,422)
        self.remote.post.assert_not_called()

    def test_auth_failure_does_not_post_and_never_leaks_session(self):
        self.remote.get.side_effect=[response(401,{})]
        result=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(result.status_code,401)
        self.assertNotIn('secret-session',result.text)
        self.remote.post.assert_not_called()

    def test_timeout_is_unknown_and_not_automatically_retried(self):
        self.remote.post.side_effect=requests.Timeout('secret-session')
        result=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(result.json()['status'],'unknown')
        self.assertNotIn('secret-session',result.text)
        again=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(again.json()['status'],'unknown')
        self.assertEqual(self.remote.post.call_count,1)

    def test_explicit_verdicts_and_duplicate_filter_are_distinct(self):
        for code,verdict,status in [(200,'WRONG','wrong'),(202,'INDETERMINATE','pending'),(412,'','rejected')]:
            self.prepare()
            self.remote.post.return_value=response(code,{'status':True,'submission':verdict,'description':'Result'})
            body={**self.body,'request_id':f'request-{code}'}
            result=self.client.post('/api/dres/submit',json=body)
            self.assertEqual(result.json()['status'],status,result.text)

    def test_exact_filename_with_extension_is_preserved_when_dres_uses_it(self):
        self.prepare(images=[{**self.remote_image,'name':'08_1115.jpg'}])
        result=self.client.post('/api/dres/submit/preview',json=self.body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['media_item_name'],'08_1115.jpg')

    def test_participant_preview_uses_client_api_and_no_admin_catalog(self):
        self.settings.return_value={'base_url':'https://dres.2hbread.com','metadata_mode':'participant','media_name_format':'stem'}
        result=self.client.post('/api/dres/submit/preview',json=self.body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.remote.get.call_count,2)
        self.remote.post.assert_not_called()
        data=result.json()
        self.assertEqual(data['resolution'],'configured_name')
        self.assertTrue(data['warnings'])
        self.assertEqual(data['payload']['answerSets'][0]['answers'],[{'mediaItemName':'08_1115'}])
        self.assertNotIn('taskName',data['payload']['answerSets'][0])

    def test_participant_submit_infers_collection_and_omits_video_time(self):
        self.settings.return_value={'base_url':'https://dres.2hbread.com','metadata_mode':'participant','media_name_format':'stem'}
        result=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(result.json()['status'],'correct',result.text)
        self.assertEqual(self.remote.get.call_count,2)
        self.assertEqual(self.remote.post.call_args.kwargs['json'],{'answerSets':[{'answers':[{'mediaItemName':'08_1115'}]}]})

    def test_browser_image_id_can_be_submitted_without_video_identifiers(self):
        self.settings.return_value={'base_url':'https://dres.2hbread.com','metadata_mode':'participant','media_name_format':'stem'}
        result=self.client.post('/api/dres/submit/preview',json={**self.body,'items':[{'image_id':'Batch1/08_1115.jpg'}]})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['media_item_name'],'08_1115')
        self.remote.post.assert_not_called()

    def test_castle5000_preview_uses_documented_prefix_and_collection(self):
        self.settings.return_value={
            'base_url':'https://dres.2hbread.com','metadata_mode':'participant',
            'media_name_format':'stem','media_name_prefix':'day1_Kitchen_',
            'collection_name':'castle5000',
        }
        result=self.client.post('/api/dres/submit/preview',json=self.body)
        self.assertEqual(result.status_code,200,result.text)
        data=result.json()
        self.assertEqual(data['image_id'],'Batch1/08_1115.jpg')
        self.assertEqual(data['filename'],'08_1115.jpg')
        self.assertEqual(data['media_item_name'],'day1_Kitchen_08_1115')
        self.assertEqual(data['collection_name'],'castle5000')
        self.assertEqual(data['payload'],{'answerSets':[{'answers':[{
            'mediaItemName':'day1_Kitchen_08_1115',
            'mediaItemCollectionName':'castle5000',
        }]}]})
        self.assertEqual(self.remote.get.call_count,2)
        self.remote.post.assert_not_called()

    def test_castle5000_submit_sends_single_image_answer_from_browser(self):
        self.settings.return_value={
            'base_url':'https://dres.2hbread.com','metadata_mode':'participant',
            'media_name_format':'stem','media_name_prefix':'day1_Kitchen_',
            'collection_name':'castle5000',
        }
        body={**self.body,'items':[{'image_id':'Batch1/08_1115.jpg'}]}
        result=self.client.post('/api/dres/submit',json=body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'correct')
        self.remote.post.assert_called_once()
        self.assertEqual(self.remote.post.call_args.args[0],
                         'https://dres.2hbread.com/api/v2/submit/run')
        self.assertEqual(self.remote.post.call_args.kwargs['params'],
                         {'session':'secret-session'})
        # Exact body: no local batch path, extension, task ID/name, or video times.
        self.assertEqual(self.remote.post.call_args.kwargs['json'],{
            'answerSets':[{'answers':[{
                'mediaItemName':'day1_Kitchen_08_1115',
                'mediaItemCollectionName':'castle5000',
            }]}],
        })

    def test_castle5000_colliding_final_names_never_submit(self):
        self.settings.return_value={
            'base_url':'https://dres.2hbread.com','metadata_mode':'participant',
            'media_name_format':'stem','media_name_prefix':'day1_Kitchen_',
            'collection_name':'castle5000',
        }
        service=self.client.app.state.service
        other=service.catalog.root/'Batch2/day1_Kitchen_08_1115.jpg'
        other.parent.mkdir()
        Image.new('RGB',(128,72),'blue').save(other)
        service.catalog=Catalog(service.catalog.root)
        result=self.client.post('/api/dres/submit',json=self.body)
        self.assertEqual(result.status_code,409,result.text)
        self.remote.post.assert_not_called()


class Castle5000NamingTests(unittest.TestCase):
    def test_default_configuration_matches_pdf_examples_and_failed_user_image(self):
        settings=load_dres_config()
        self.assertEqual(settings['metadata_mode'],'participant')
        self.assertEqual(settings['collection_name'],'castle5000')
        for filename,expected in [
            ('10_1528.jpg','day1_Kitchen_10_1528'),
            ('08_102.jpg','day1_Kitchen_08_102'),
            ('20_3499.jpg','day1_Kitchen_20_3499'),
            ('09_1573.jpg','day1_Kitchen_09_1573'),
        ]:
            with self.subTest(filename=filename):
                self.assertEqual(configured_media_name(Path('Batch1')/filename,settings),expected)

    def test_prefix_is_idempotent_and_excludes_windows_parent_directories(self):
        settings=load_dres_config()
        for local_path in [
            PureWindowsPath(r'D:\UIT\DS\DS314\dsreborn\data\Batch1\09_1573.jpg'),
            Path('Batch3/09_1573.jpg'),
            Path('Batch2/day1_Kitchen_09_1573.jpg'),
        ]:
            with self.subTest(path=str(local_path)):
                self.assertEqual(configured_media_name(local_path,settings),'day1_Kitchen_09_1573')
