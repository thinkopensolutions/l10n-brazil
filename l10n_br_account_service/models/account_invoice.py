# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
# Copyright (C) 2009  Renato Lima - Akretion                                  #
#                                                                             #
# This program is free software: you can redistribute it and/or modify        #
# it under the terms of the GNU Affero General Public License as published by #
# the Free Software Foundation, either version 3 of the License, or           #
# (at your option) any later version.                                         #
#                                                                             #
# This program is distributed in the hope that it will be useful,             #
# but WITHOUT ANY WARRANTY; without even the implied warranty of              #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the               #
# GNU Affero General Public License for more details.                         #
#                                                                             #
# You should have received a copy of the GNU Affero General Public License    #
# along with this program.  If not, see <http://www.gnu.org/licenses/>.       #
###############################################################################

from lxml import etree

from openerp import models, fields, api

from openerp.addons.l10n_br_account.models.account_invoice import (
    OPERATION_TYPE)

from .l10n_br_account_service import (
    PRODUCT_FISCAL_TYPE,
    PRODUCT_FISCAL_TYPE_DEFAULT)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def _default_fiscal_document(self):
        company = self.env['res.company'].browse(self.env.user.company_id.id)
        return company.service_invoice_id

    @api.model
    def _default_fiscal_document_serie(self):
        company = self.env['res.company'].browse(self.env.user.company_id.id)
        return company.document_serie_service_id

    @api.model
    @api.returns('l10n_br_account.fiscal_category')
    def _default_fiscal_category(self):
        DEFAULT_FCATEGORY_SERVICE = {
            'in_invoice': 'in_invoice_service_fiscal_category_id',
            'out_invoice': 'out_invoice_service_fiscal_category_id',
            'in_refund': 'out_invoice_service_fiscal_category_id',
            'out_refund': 'in_invoice_service_fiscal_category_id'
        }
        default_fo_category = {'service': DEFAULT_FCATEGORY_SERVICE}
        invoice_type = self._context.get('type', 'out_invoice')
        invoice_fiscal_type = self._context.get('fiscal_type', 'service')
        company = self.env['res.company'].browse(self.env.user.company_id.id)
        return company[default_fo_category[invoice_fiscal_type][invoice_type]]

    fiscal_type = fields.Selection(PRODUCT_FISCAL_TYPE,
                                   'Tipo Fiscal',
                                   required=True,
                                   default=PRODUCT_FISCAL_TYPE_DEFAULT)
    fiscal_category_id = fields.Many2one(
        'l10n_br_account.fiscal.category', 'Categoria Fiscal',
        readonly=True, states={'draft': [('readonly', False)]},
        default=_default_fiscal_category)

    fiscal_document_id = fields.Many2one(
        'l10n_br_account.fiscal.document', 'Documento', readonly=True,
        states={'draft': [('readonly', False)]},
        default=_default_fiscal_document)
    fiscal_document_electronic = fields.Boolean(
        related='fiscal_document_id.electronic')
    document_serie_id = fields.Many2one(
        'l10n_br_account.document.serie', u'Série',
        domain="[('fiscal_document_id', '=', fiscal_document_id),\
        ('company_id','=',company_id)]", readonly=True,
        states={'draft': [('readonly', False)]},
        default=_default_fiscal_document_serie)
    state = fields.Selection(selection_add=[
                         ('nfse_export', u'Enviar para Prefeitura'),
                         ('nfse_issuing', u'WAITING FOR ISSUING APPROVAL'),
                         ('nfse_exception', u'Erro de autorização da Prefeitura'),
                         ('nfse_cancelled', u'Waiting for Cancellation'),
                         ('nfse_denied', u'Denegada na Prefeitura')])
    
    nfse_description = fields.Text('NFS-e Description')
    
    @api.multi
    def nfse_check(self):
        for record in self:
            return True
        
    
    @api.one    
    def nfse_issue(self):
        self.write({'state': 'nfse_issuing'})
        return True
    @api.one   
    def check_nfse_status(self):
        #consult status of nfse and update
        self.signal_workflow('invoice_open_nfse')
        return True
    
    def nfse_cancel(self):
        self.write({'state': 'nfse_cancelled'})
        return True
    
    #open : when nfse is issued
    #nfse_exception : when there is some unexpected issue in generating nfse
    #nfse_denied : when nfse fails in authorization
    @api.one
    def action_invoice_send_nfse(self):
        self.write({'state' : 'open'})
        #self.write({'state' : 'nfse_exception'})
        #self.write({'state' : 'nfse_denied'})
        return True
    
    @api.multi
    def nfse_cancel(self):
        self.ensure_one()
        if self.type == 'out_invoice' and self.fiscal_document_electronic == True and self.state in ['open', 'invoice_issuing']:
            self.write({'state' : 'nfse_cancelled'})
            return True
        else:
            #cancel nfse here
            return self.button_cancel()
        
        
        
    def button_cancel(self, cr, uid, ids, context=None):
        assert len(ids) == 1, ('This option should only be used for a single '
                               'id at a time.')
        if context is None:
            context = {}
        inv = self.browse(cr, uid, ids[0], context=context)
        return super(AccountInvoice, self).action_cancel(cr, uid, [inv.id], context)


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    # TODO migrate to new API
    def fields_view_get(self, cr, uid, view_id=None, view_type=False,
                        context=None, toolbar=False, submenu=False):

        result = super(AccountInvoiceLine, self).fields_view_get(
            cr, uid, view_id=view_id, view_type=view_type, context=context,
            toolbar=toolbar, submenu=submenu)

        if context is None:
            context = {}

        if view_type == 'form':
            eview = etree.fromstring(result['arch'])

            if 'type' in context.keys():
                cfops = eview.xpath("//field[@name='cfop_id']")
                for cfop_id in cfops:
                    cfop_id.set('domain', "[('type','=','%s')]" % (
                        OPERATION_TYPE[context['type']],))
                    cfop_id.set('required', '1')

            if context.get('fiscal_type', False) == 'service':

                cfops = eview.xpath("//field[@name='cfop_id']")
                for cfop_id in cfops:
                    cfop_id.set('invisible', '1')
                    cfop_id.set('required', '0')

            result['arch'] = etree.tostring(eview)

        return result
    
    # set type_tax_use so that It can get taxes from company
    @api.multi
    def product_id_change(self, product, uom_id, qty=0, name='',
                          type='out_invoice', partner_id=False,
                          fposition_id=False, price_unit=False,
                          currency_id=False, company_id=None):
        ctx = dict(self.env.context)
        if type in ('out_invoice', 'out_refund'):
            ctx.update({'type_tax_use': 'sale'})
        else:
            ctx.update({'type_tax_use': 'purchase'})
        self = self.with_context(ctx)
        result = super(AccountInvoiceLine, self).product_id_change(
            product, uom_id, qty, name, type, partner_id,
            fposition_id, price_unit, currency_id, company_id)
        return result
