# -*- coding: utf-8 -*-

# Copyright (c) 2015 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from bson import ObjectId
from decimal import Decimal

from django.conf import settings

from wstore.rss_adaptor.rss_adaptor import RSSAdaptorThread
from wstore.store_commons.database import get_database_connection


class CDRManager(object):

    _order = None

    def __init__(self, order, contract):
        self._offering = contract.offering
        self._init_cdr_info(order, contract)

    def _init_cdr_info(self, order, contract):
        # Set offering ID
        offering = self._offering.off_id + ' ' + self._offering.name + ' ' + self._offering.version

        # Get the provider (Organization)
        provider = self._offering.owner_organization.name

        # Get the customer
        customer = order.owner_organization.name
        currency = contract.pricing_model['general_currency']

        self._cdr_info = {
            'provider': provider,
            'offering': offering,
            'customer': customer,
            'product_class': contract.revenue_class,
            'cost_currency': currency,
            'order': order.order_id + ' ' + contract.item_id
        }

    def _generate_cdr_part(self, part, event, description):
        # Create connection for raw database access
        db = get_database_connection()

        # Take and increment the correlation number using
        # the mongoDB atomic access in order to avoid race
        # problems
        corr_number = db.wstore_organization.find_and_modify(
            query={'_id': ObjectId(self._offering.owner_organization.pk)},
            update={'$inc': {'correlation_number': 1}}
        )['correlation_number']

        cdr_part = {
            'correlation': unicode(corr_number),
            'cost_value': unicode(part['value']),
            'tax_value': unicode(Decimal(part['value']) - Decimal(part['duty_free'])),
            'event': event,
            'description': description
        }

        cdr_part.update(self._cdr_info)
        return cdr_part

    def generate_cdr(self, applied_parts, time_stamp):

        cdrs = []

        self._cdr_info['time_stamp'] = time_stamp
        self._cdr_info['type'] = 'C'

        # Check the type of the applied parts
        if 'single_payment' in applied_parts:

            # A cdr is generated for every price part
            for part in applied_parts['single_payment']:
                description = 'One time payment: ' + unicode(part['value']) + ' ' + self._cdr_info['cost_currency']
                cdrs.append(self._generate_cdr_part(part, 'One time payment event', description))

        if 'subscription' in applied_parts:

            # A cdr is generated by price part
            for part in applied_parts['subscription']:
                description = 'Recurring payment: ' + unicode(part['value']) + ' ' + self._cdr_info['cost_currency'] \
                              + ' ' + part['unit']

                cdrs.append(self._generate_cdr_part(part, 'Recurring payment event', description))

        if 'accounting' in applied_parts:

            # A cdr is generated by price part
            for part in applied_parts['accounting']:
                use_part = {
                    'value': part['price'],
                    'duty_free': part['duty_free'],
                }

                # Calculate the total consumption
                use = 0
                for sdr in part['accounting']:
                    use += int(sdr['value'])
                    description = 'Fee per ' + part['model']['unit'] + ', Consumption: ' + unicode(use)

                cdrs.append(self._generate_cdr_part(use_part, 'Pay per use event', description))

        # Send the created CDRs to the Revenue Sharing System
        r = RSSAdaptorThread(cdrs)
        r.start()

    def refund_cdrs(self, price, duty_free, time_stamp):
        self._cdr_info['time_stamp'] = time_stamp
        self._cdr_info['type'] = 'R'

        # Create a payment part representing the whole payment
        aggregated_part = {
            'value': price,
            'duty_free': duty_free,
        }

        description = 'Refund event: ' + unicode(price) + ' ' + self._cdr_info['cost_currency']
        cdrs = [self._generate_cdr_part(aggregated_part, 'Refund event', description)]

        # Send the created CDRs to the Revenue Sharing System
        r = RSSAdaptorThread(cdrs)
        r.start()
