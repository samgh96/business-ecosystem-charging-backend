# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid

# This file is part of WStore.

# WStore is free software: you can redistribute it and/or modify
# it under the terms of the European Union Public Licence (EUPL)
# as published by the European Commission, either version 1.1
# of the License, or (at your option) any later version.

# WStore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# European Union Public Licence for more details.

# You should have received a copy of the European Union Public Licence
# along with WStore.
# If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.

import json
import types
from mock import MagicMock
from nose_parameterized import parameterized
from urllib2 import HTTPError

from django.test import TestCase
from django.test.client import RequestFactory
from django.contrib.auth.models import User

from wstore.admin.organizations import views
from wstore.models import Organization
from wstore.store_commons.utils.testing import decorator_mock, build_response_mock,\
decorator_mock_callable, HTTPResponseMock
from wstore.admin.rss.tests import ExpenditureMock


class OrganizationChangeTestCase(TestCase):

    tags = ('fiware-ut-25',)

    def setUp(self):
        # Create request factory
        self.factory = RequestFactory()
        # Create testing user
        self.user = User.objects.create_user(username='test_user', email='', password='passwd')
        # Create testing request
        self.data = {
            'organization': 'test_org'
        }
        self.request = self.factory.put(
            '/administration/organizations/change',
            json.dumps(self.data),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.request.user = self.user

    def test_organization_change(self):

        org = Organization.objects.create(
            name='test_org'
        )
        # Update user profile info
        self.user.userprofile.organizations.append({
            'organization': org.pk
        })
        self.user.userprofile.save()

        response = views.change_current_organization(self.request)
        self.user = User.objects.get(username='test_user')
        self.assertEquals(self.user.userprofile.current_organization.pk, org.pk)

        body_response = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(body_response['message'], 'OK')
        self.assertEquals(body_response['result'], 'correct')

    def test_organization_change_errors(self):

        errors = [
            'Not found',
            'Forbidden'
        ]
        for i in [0, 1]:
            if i == 1:
                Organization.objects.create(
                    name='test_org'
                )

            response = views.change_current_organization(self.request)

            body_response = json.loads(response.content)
            self.assertEquals(body_response['message'], errors[i])
            self.assertEquals(body_response['result'], 'error')


class OrganizationEntryTestCase(TestCase):

    tags = ('org-admin',)

    @classmethod
    def setUpClass(cls):
        from wstore.store_commons.utils import http
        # Save the reference of the decorators
        cls._old_auth = types.FunctionType(
            http.authentication_required.func_code,
            http.authentication_required.func_globals,
            name=http.authentication_required.func_name,
            argdefs=http.authentication_required.func_defaults,
            closure=http.authentication_required.func_closure
        )

        cls._old_supp = types.FunctionType(
            http.supported_request_mime_types.func_code,
            http.supported_request_mime_types.func_globals,
            name=http.supported_request_mime_types.func_name,
            argdefs=http.supported_request_mime_types.func_defaults,
            closure=http.supported_request_mime_types.func_closure
        )

        # Mock class decorators
        http.authentication_required = decorator_mock
        http.supported_request_mime_types = decorator_mock_callable

        reload(views)
        views.build_response = build_response_mock
        views.HttpResponse = HTTPResponseMock
        views.RSS = MagicMock()
        rss_object = MagicMock()
        views.RSS.objects.all.return_value = [rss_object]
        views.ExpenditureManager = MagicMock()

        views._check_limits = MagicMock()
        views._check_limits.return_value = {
            'currency': 'EUR',
            'perTransaction': '100',
            'weekly': '150'
        }
        super(OrganizationEntryTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        # Restore mocked decorators
        from wstore.store_commons.utils import http
        http.authentication_required = cls._old_auth
        http.supported_request_mime_types = cls._old_supp
        super(OrganizationEntryTestCase, cls).tearDownClass()

    def setUp(self):
        # Create request user mock
        user_object = MagicMock()
        user_object.username = 'test_user'
        user_object.pk = '1111'
        user_object.is_staff = False
        self.request = MagicMock()
        self.request.user = user_object

        # Create organization mock
        self.org_object = MagicMock()
        self.org_object.name = 'test_org'
        self.org_object.managers = ['1111']
        self.org_object.payment_info = {
            'number': '4567456745674567'
        }
        views.Organization = MagicMock()
        views.Organization.objects.get.return_value = self.org_object

    def _mock_expenditure_401(self):
        exp_mock = ExpenditureMock()
        views.ExpenditureManager = exp_mock.ExpenditureManager

    def _not_found(self):
        views.Organization.objects.get.side_effect = Exception('')

    def _forbidden(self):
        self.org_object.managers = []

    def _unauthorized(self):
        views.ExpenditureManager = MagicMock()
        exp_object = MagicMock()
        exp_object.set_actor_limit.side_effect = HTTPError('http://rss.test.com', 401, 'Unauthorized', None, None)
        views.ExpenditureManager.return_value = exp_object

    def _rss_failure(self):
        views.ExpenditureManager = MagicMock()
        exp_object = MagicMock()
        exp_object.set_actor_limit.side_effect = HTTPError('http://rss.test.com', 500, 'Server error', None, None)
        views.ExpenditureManager.return_value = exp_object

    @parameterized.expand([
    ({
        'notification_url': 'http://notificationurl.com',
        'tax_address': {
            'street': 'fake street 123',
            'country': 'Country',
            'city': 'City',
            'postal': '12345'
        },
        'payment_info': {
            'number': '1234123412341234',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        },
        'limits': {
            'perTransaction': '100',
            'weekly': '150'
        }
    }, (200, 'OK', 'correct'), False),
    ({
        'payment_info': {
            'number': 'xxxxxxxxxxxx4567',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        },
        'limits': {
            'perTransaction': '100',
            'weekly': '150'
        }
    }, (200, 'OK', 'correct'), False, _mock_expenditure_401),
    ({}, (200, 'OK', 'correct'), False),
    ({}, (404, 'Organization not found', 'error'), True, _not_found),
    ({}, (403, 'Forbidden', 'error'), True, _forbidden),
    ({
        'notification_url': 'invalidurl'
    }, (400, 'Enter a valid URL', 'error'), True),
    ({
        'limits': {
            'perTransaction': '100',
            'weekly': '150'
        }
    }, (400, 'Invalid JSON content', 'error'), True, _unauthorized),
    ({
        'limits': {
            'perTransaction': '100',
            'weekly': '150'
        }
    }, (400, 'Invalid JSON content', 'error'), True, _rss_failure),
    ({
        'payment_info': {
            'number': '1234',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        }
    }, (400, 'Invalid credit card number', 'error'), True),
    ])
    def test_update_organization(self, data, exp_resp, error, side_effect=None):
        # Create object
        org_entry = views.OrganizationEntry(permitted_methods=('GET', 'PUT'))

        # Include data
        self.request.raw_post_data = json.dumps(data)

        if side_effect:
            side_effect(self)

        # Call the view
        response = org_entry.update(self.request, 'test_org')

        # Check response
        content = json.loads(response.content)
        self.assertEquals(response.status_code, exp_resp[0])
        self.assertEquals(content['message'], exp_resp[1])
        self.assertEquals(content['result'], exp_resp[2])

        # Check values
        if not error:
            if 'notification_url' in data:
                self.assertEquals(data['notification_url'], self.org_object.notification_url)

            if 'tax_address' in data:
                self.assertEquals(data['tax_address'], self.org_object.tax_address)

            if 'payment_info' in data:
                if not data['payment_info']['number'].startswith('x'):
                    self.assertEquals(data['payment_info'], self.org_object.payment_info)
                else:
                    data['payment_info']['number'] = '4567456745674567'

            if 'limits' in data:
                data['limits']['currency'] = 'EUR'
                self.assertEquals(data['limits'], self.org_object.expenditure_limits)

    def _revoke_staff(self):
        self.request.user.is_staff = False

    @parameterized.expand([
    (False, False, ),
    (False, True, _revoke_staff),
    (True, False, _not_found)
    ])
    def test_get_organization(self, error, not_staff, side_effect=None):

        self.request.user.is_staff = True
        # Mock get_organization_info
        data = {
            'name': 'test_org1',
            'notification_url': 'http://notificationurl.com',
            'payment_info': {
                'number': 'xxxxxxxxxxxx1234',
                'type': 'visa',
                'expire_year': '2018',
                'expire_month': '5',
                'cvv2': '111'
            }
        }
        views.get_organization_info = MagicMock()
        views.get_organization_info.return_value = data.copy()

        # Mock organization all method
        org_object = MagicMock()
        views.Organization.objects.get = MagicMock()
        views.Organization.objects.return_value = org_object

        # Create the view
        org_entry = views.OrganizationEntry(permitted_methods=('GET', 'PUT'))

        if side_effect:
            side_effect(self)

        response = org_entry.read(self.request, 'test_org')

        if not error:
            # Check response
            if not_staff:
                del(data['payment_info'])

            self.assertEquals(response.status, 200)
            self.assertEquals(json.loads(response.data), data)
        else:
            body_response = json.loads(response.content)
            self.assertEquals(response.status_code, 404)
            self.assertEquals(body_response['message'], 'Not found')
            self.assertEquals(body_response['result'], 'error')


class OrganizationCollectionTestCase(TestCase):

    tags = ('org-admin',)

    @classmethod
    def setUpClass(cls):
        from wstore.store_commons.utils import http
        # Save the reference of the decorators
        cls._old_auth = types.FunctionType(
            http.authentication_required.func_code,
            http.authentication_required.func_globals,
            name=http.authentication_required.func_name,
            argdefs=http.authentication_required.func_defaults,
            closure=http.authentication_required.func_closure
        )

        cls._old_supp = types.FunctionType(
            http.supported_request_mime_types.func_code,
            http.supported_request_mime_types.func_globals,
            name=http.supported_request_mime_types.func_name,
            argdefs=http.supported_request_mime_types.func_defaults,
            closure=http.supported_request_mime_types.func_closure
        )

        # Mock class decorators
        http.authentication_required = decorator_mock
        http.supported_request_mime_types = decorator_mock_callable

        reload(views)
        views.build_response = build_response_mock
        views.HttpResponse = HTTPResponseMock
        super(OrganizationCollectionTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        # Restore mocked decorators
        from wstore.store_commons.utils import http
        http.authentication_required = cls._old_auth
        http.supported_request_mime_types = cls._old_supp
        super(OrganizationCollectionTestCase, cls).tearDownClass()

    def setUp(self):
        # Create organization mock 1
        org_mock_1 = MagicMock()
        org_mock_1.private = False
        org_mock_1.name = 'test_org1'
        org_mock_1.notification_url = 'http://notification.com'
        org_mock_1.tax_address = {
            'street': 'fake street 123',
            'country': 'Country'
        }
        org_mock_1.expenditure_limits = {}
        org_mock_1.payment_info = {
            'number': '1234123412341234',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        }

        # Create organization mock 2
        org_mock_2 = MagicMock()
        org_mock_2.private = False
        org_mock_2.name = 'test_org2'
        org_mock_2.notification_url = 'http://notification2.com'
        org_mock_2.expenditure_limits = {}

        # Create organization mock 3
        org_mock_3 = MagicMock()
        org_mock_3.private = True

        self.organizations = {
            'org1': org_mock_1,
            'org2': org_mock_2,
            'org3': org_mock_3
        }
        # Create request mock
        self.request = MagicMock()
        self.request.user.is_staff = True

        # Create organization object mock
        views.Organization = MagicMock()

    @parameterized.expand([
    ({
        'name': 'test_org1',
        'notification_url': 'http://notification.com',
        'tax_address': {
            'street': 'fake street 123',
            'country': 'Country'
        },
        'payment_info': {
            'number': 'xxxxxxxxxxxx1234',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        },
        'limits': {},
        'is_manager': False
    }, 'org1'),
    ({
        'name': 'test_org2',
        'notification_url': 'http://notification2.com',
        'limits': {},
        'is_manager': False
    }, 'org2'),
    ('Private organization', 'org3', True)
    ])
    def test_get_organization_info(self, exp_data, org_id, exp_error=False):

        # Call the mocked function
        error = False
        msg = None
        try:
            org_info = views.get_organization_info(self.organizations[org_id])
        except Exception as e:
            error = True
            msg = e.message

        if not exp_error:
            # Check organization info
            self.assertFalse(error)
            self.assertEquals(org_info, exp_data)
        else:
            self.assertTrue(error)
            self.assertEquals(msg, exp_data)

    def _not_found(self):
        views.Organization.objects.filter.return_value = []

    def _found(self):
        org = MagicMock()
        views.Organization.objects.filter.return_value = [org]

    @parameterized.expand([
    ({
        'name': 'test_org1',
        'notification_url': 'http://notificationurl.com',
        'tax_address': {
            'city': 'city',
            'street': 'fake street 123',
            'country': 'country',
            'postal': '12344'
        },
        'payment_info': {
            'number': '1234123412341234',
            'type': 'visa',
            'expire_year': '2018',
            'expire_month': '5',
            'cvv2': '111'
        }
    }, (201, 'Created', 'correct'), True, _not_found),
    ({
        'name': 'test_org1',
        'notification_url': 'http://notificationurl.com'
    }, (201, 'Created', 'correct')),
    ({
        'invalid_name': 'test_org1',
        'notification_url': 'http://notificationurl.com'
    }, (400, 'Invalid JSON content', 'error'), False),
    ({
        'name': 'test_org1',
        'notification_url': 'http://notificationurl.com'
    }, (400, 'The test_org1 organization is already registered.', 'error'), False, _found),
    ({
        'name': 'test_org1',
        'notification_url': 'http:notificationurl.com'
    }, (400, 'Enter a valid URL', 'error'), False , _not_found)
    ])
    def test_organization_creation(self, data, exp_resp, created=True, side_effect=None):

        # Load request data
        self.request.raw_post_data = json.dumps(data)

        if side_effect:
            side_effect(self)

        # Create the view
        org_collection = views.OrganizationCollection(permitted_methods=('POST', 'GET'))

        # Call the view
        response = org_collection.create(self.request)

        # Check response
        content = json.loads(response.content)
        self.assertEquals(response.status_code, exp_resp[0])
        self.assertEquals(content['message'], exp_resp[1])
        self.assertEquals(content['result'], exp_resp[2])

        # Check calls
        if created:
            tax = {}
            if 'tax_address' in data:
                tax = data['tax_address']

            pay = {}
            if 'payment_info' in data:
                pay = data['payment_info']

            views.Organization.objects.create.assert_called_with(
                name=data['name'],
                notification_url=data['notification_url'],
                tax_address=tax,
                payment_info=pay,
                private=False
            )

    def _revoke_staff(self):
        self.request.user.is_staff = False

    @parameterized.expand([
    (False, ),
    (True, _revoke_staff),
    ])
    def test_organization_retrieving(self, not_staff, side_effect=None):

        # Mock get_organization_info
        data = {
            'name': 'test_org1',
            'notification_url': 'http://notificationurl.com',
            'payment_info': {
                'number': 'xxxxxxxxxxxx1234',
                'type': 'visa',
                'expire_year': '2018',
                'expire_month': '5',
                'cvv2': '111'
            }
        }
        views.get_organization_info = MagicMock()
        views.get_organization_info.return_value = data.copy()

        # Mock organization all method
        views.Organization.objects.all.return_value = [self.organizations['org1'], self.organizations['org2']]

        # Create the view
        org_collection = views.OrganizationCollection(permitted_methods=('POST', 'GET'))

        if side_effect:
            side_effect(self)

        response = org_collection.read(self.request)

        # Check response
        if not_staff:
            del(data['payment_info'])

        self.assertEquals(response.status, 200)
        self.assertEquals(json.loads(response.data), [data, data])
