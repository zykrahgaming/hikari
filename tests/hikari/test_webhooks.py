# -*- coding: utf-8 -*-
# Copyright (c) 2020 Nekokatt
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import mock

from hikari import webhooks


def test_WebhookType_str_operator():
    type = webhooks.WebhookType(1)
    assert str(type) == "INCOMING"


def test_Webhook_str_operator():
    mock_webhook = mock.Mock(webhooks.Webhook)
    mock_webhook.name = "not a webhook"
    assert webhooks.Webhook.__str__(mock_webhook) == "not a webhook"


def test_Webhook_str_operator_when_name_is_None():
    mock_webhook = mock.Mock(webhooks.Webhook, id=987654321)
    mock_webhook.name = None
    assert webhooks.Webhook.__str__(mock_webhook) == "Unnamed webhook ID 987654321"