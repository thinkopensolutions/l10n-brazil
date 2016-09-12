# -*- coding: utf-8 -*-
###############################################################################
#                                                                             #
# Copyright (C) 2009 - TODAY Renato Lima - Akretion                           #
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

from openerp import models, fields, api, _
from openerp.addons import decimal_precision as dp
from openerp.exceptions import except_orm
from openerp.exceptions import Warning as UserError

from .l10n_br_account import PRODUCT_FISCAL_TYPE, PRODUCT_FISCAL_TYPE_DEFAULT

OPERATION_TYPE = {
    'out_invoice': 'output',
    'in_invoice': 'input',
    'out_refund': 'input',
    'in_refund': 'output'
}

JOURNAL_TYPE = {
    'out_invoice': 'sale',
    'in_invoice': 'purchase',
    'out_refund': 'sale_refund',
    'in_refund': 'purchase_refund'
}


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.one
    @api.depends(
        'move_id.line_id.reconcile_id.line_id',
        'move_id.line_id.reconcile_partial_id.line_partial_ids',
    )
    def _compute_receivables(self):
        lines = self.env['account.move.line']
        for line in self.move_id.line_id:
            if line.account_id.id == self.account_id.id and \
                line.account_id.type in ('receivable', 'payable') and \
                    self.journal_id.revenue_expense:
                lines |= line
        self.move_line_receivable_id = (lines).sorted()

    @api.model
    def _default_fiscal_document(self):
        company = self.env['res.company'].browse(self.env.user.company_id.id)
        return company.service_invoice_id

    @api.model
    def _default_fiscal_document_serie(self):
        company = self.env['res.company'].browse(self.env.user.company_id.id)
        return company.document_serie_service_id
    
    
    #compute amount to consider withholdings
    # this method will correct value of total and liquid
    @api.one
    @api.depends('invoice_line.price_subtotal', 'tax_line.amount')
    def _compute_amount(self):
        self.amount_gross = sum(line.price_gross for line in self.invoice_line)
        self.amount_untaxed = self.amount_gross - self.amount_discount
        self.amount_tax = sum(tax.amount
                              for tax in self.tax_line)
        amount_tax_with_tax_discount= sum(tax.amount for tax in self.tax_line if tax.tax_code_id.tax_discount) \
                       - sum(tax.amount for tax in self.withholding_tax_lines if tax.tax_code_id.tax_discount)
        amount_tax_without_tax_discount = sum(tax.amount for tax in self.tax_line if not tax.tax_code_id.tax_discount) \
                       - sum(tax.amount for tax in self.withholding_tax_lines if not tax.tax_code_id.tax_discount)
        self.amount_total = self.amount_untaxed + \
            amount_tax_without_tax_discount - self.amount_tax_withholding
        self.amount_total_liquid = self.amount_untaxed - amount_tax_with_tax_discount  - self.amount_tax_withholding

    issuer = fields.Selection(
        [('0', u'Emissão própria'), ('1', 'Terceiros')], 'Emitente',
        default='0', readonly=True, states={'draft': [('readonly', False)]})
    internal_number = fields.Char(
        'Invoice Number', size=32, readonly=True,
        states={'draft': [('readonly', False)]},
        help="""Unique number of the invoice, computed
            automatically when the invoice is created.""")
    fiscal_type = fields.Selection(
        PRODUCT_FISCAL_TYPE, 'Tipo Fiscal', required=True,
        default=PRODUCT_FISCAL_TYPE_DEFAULT)
    vendor_serie = fields.Char(
        'Série NF Entrada', size=12, readonly=True,
        states={'draft': [('readonly', False)]},
        help=u"Série do número da Nota Fiscal do Fornecedor")
    move_line_receivable_id = fields.Many2many(
        'account.move.line', string='Receivables',
        compute='_compute_receivables')
    document_serie_id = fields.Many2one(
        'l10n_br_account.document.serie', string=u'Série',
        domain="[('fiscal_document_id', '=', fiscal_document_id),\
        ('company_id','=',company_id)]", readonly=True,
        states={'draft': [('readonly', False)]},
        default=_default_fiscal_document_serie)
    fiscal_document_id = fields.Many2one(
        'l10n_br_account.fiscal.document', string='Documento', readonly=True,
        states={'draft': [('readonly', False)]},
        default=_default_fiscal_document)
    fiscal_document_electronic = fields.Boolean(
        related='fiscal_document_id.electronic', type='boolean', readonly=True,
        store=True, string='Electronic')
    fiscal_category_id = fields.Many2one(
        'l10n_br_account.fiscal.category', 'Categoria Fiscal',
        readonly=True, states={'draft': [('readonly', False)]})
    fiscal_position = fields.Many2one(
        'account.fiscal.position', 'Fiscal Position', readonly=True,
        states={'draft': [('readonly', False)]},
        domain="[('fiscal_category_id','=',fiscal_category_id)]")
    account_document_event_ids = fields.One2many(
        'l10n_br_account.document_event', 'document_event_ids',
        u'Eventos')
    fiscal_comment = fields.Text(u'Observação Fiscal')
    cnpj_cpf = fields.Char(
        string=u'CNPJ/CPF',
        related='partner_id.cnpj_cpf',
    )
    legal_name = fields.Char(
        string=u'Razão Social',
        related='partner_id.legal_name',
    )
    ie = fields.Char(
        string=u'Inscrição Estadual',
        related='partner_id.inscr_est',
    )
    amount_gross = fields.Float(string='Vlr. Bruto',store=True, digits=dp.get_precision('Account'), compute='get_amount_tax_withholding', readonly=True)
    amount_tax_withholding = fields.Float(compute='get_amount_tax_withholding', string='Withholdings', digits=dp.get_precision('Account'), store=True)
    amount_total_liquid = fields.Float(compute='_compute_amount', string='Liquid', digits=dp.get_precision('Account'), store=True)
    withholding_tax_lines = fields.One2many('withholding.tax.line','invoice_id','Withholding Lines',copy=True)
    amount_discount = fields.Float(string='Desconto', store=True, digits=dp.get_precision('Account'),
                                   compute='_compute_amount')

    _order = 'internal_number desc'
    
    
    @api.multi
    def onchange_company_id(self, company_id, part_id, type,
                            invoice_line, currency_id):
        result = super(AccountInvoice, self).onchange_company_id(
            company_id, part_id, type, invoice_line,
            currency_id)

        if company_id:
            
            fiscal_comment = self.env['res.company'].browse(company_id).fiscal_comment
            result['value'].update({'fiscal_comment' : fiscal_comment})
        return result

    
    
    
    @api.one
    @api.depends('invoice_line.price_subtotal', 'withholding_tax_lines.amount','withholding_tax_lines','amount_tax')
    def get_amount_tax_withholding(self):
        total_withholding = 0.0
        for line in self.withholding_tax_lines:
            total_withholding += line.amount
        self.amount_tax_withholding = total_withholding




            #this method will reset taxes lines and withholding lines
    #we do not call super because super also will create tax lines
    @api.multi
    def button_reset_taxes(self):
        account_invoice_tax = self.env['account.invoice.tax']
        account_withholding_tax = self.env['withholding.tax.line']
        ctx = dict(self._context)
        for invoice in self:
            self._cr.execute("DELETE FROM withholding_tax_line WHERE invoice_id=%s AND manual is False", (invoice.id,))
            self._cr.execute("DELETE FROM account_invoice_tax WHERE invoice_id=%s AND manual is False", (invoice.id,))
            self.invalidate_cache()
            partner = invoice.partner_id
            if partner.lang:
                ctx['lang'] = partner.lang
            #get tax lines
            invoice_taxes = account_invoice_tax.compute(invoice.with_context(ctx))
            #get withholding lines
            withholding_taxes = account_withholding_tax.compute_withholding(invoice.with_context(ctx))
            # correct amount in tax line by subtracting withholding amount of line
            for w_key in withholding_taxes.keys():
                if w_key in invoice_taxes.keys():
                    invoice_taxes[w_key]['amount'] = invoice_taxes[w_key]['amount'] - withholding_taxes[w_key]['amount']
            # create tax lines
            for taxe in invoice_taxes.values():
                account_invoice_tax.create(taxe)
            # crate withholding lines
            for taxe in withholding_taxes.values():
                account_withholding_tax.create(taxe)
        # dummy write on self to trigger re computations
        #not calling super otherwise it will overwrite functionality 
        return self.with_context(ctx).write({'invoice_line': []})
    
    @api.multi
    def check_tax_lines(self, compute_taxes):
        super(AccountInvoice,self).check_tax_lines(compute_taxes)
        account_withholding_tax = self.env['withholding.tax.line']
        company_currency = self.company_id.currency_id
        if not self.withholding_tax_lines:
            compute_taxes = account_withholding_tax.compute_withholding(self.with_context(lang=self.partner_id.lang))
            for tax in compute_taxes.values():
                account_withholding_tax.create(tax)

    @api.one
    @api.constrains('number')
    def _check_invoice_number(self):
        domain = []
        if self.number:
            fiscal_document = self.fiscal_document_id and\
                self.fiscal_document_id.id or False
            domain.extend([('internal_number', '=', self.number),
                           ('fiscal_type', '=', self.fiscal_type),
                           ('fiscal_document_id', '=', fiscal_document)
                           ])
            if self.issuer == '0':
                domain.extend([
                    ('company_id', '=', self.company_id.id),
                    ('internal_number', '=', self.number),
                    ('fiscal_document_id', '=', self.fiscal_document_id.id),
                    ('issuer', '=', '0')])
            else:
                domain.extend([
                    ('partner_id', '=', self.partner_id.id),
                    ('vendor_serie', '=', self.vendor_serie),
                    ('issuer', '=', '1')])

            invoices = self.env['account.invoice'].search(domain)
            if len(invoices) > 1:
                raise UserError(u'Não é possível registrar documentos\
                              fiscais com números repetidos.')

    _sql_constraints = [
        ('number_uniq', 'unique(number, company_id, journal_id,\
         type, partner_id)', 'Invoice Number must be unique per Company!'),
    ]

    # TODO não foi migrado por causa do bug github.com/odoo/odoo/issues/1711
    def fields_view_get(self, cr, uid, view_id=None, view_type=False,
                        context=None, toolbar=False, submenu=False):
        result = super(AccountInvoice, self).fields_view_get(
            cr, uid, view_id=view_id, view_type=view_type, context=context,
            toolbar=toolbar, submenu=submenu)

        if context is None:
            context = {}

        if not view_type:
            view_id = self.pool.get('ir.ui.view').search(
                cr, uid, [('name', '=', 'account.invoice.tree')])
            view_type = 'tree'

        if view_type == 'form':
            eview = etree.fromstring(result['arch'])

            if 'type' in context.keys():
                fiscal_types = eview.xpath("//field[@name='invoice_line']")
                for fiscal_type in fiscal_types:
                    fiscal_type.set(
                        'context', "{'type': '%s', 'fiscal_type': '%s'}" % (
                            context['type'],
                            context.get('fiscal_type', 'service')))

                fiscal_categories = eview.xpath(
                    "//field[@name='fiscal_category_id']")
                for fiscal_category_id in fiscal_categories:
                    fiscal_category_id.set(
                        'domain',
                        """[('fiscal_type', '=', '%s'), ('type', '=', '%s'),
                        ('state', '=', 'approved'),
                        ('journal_type', '=', '%s')]"""
                        % (context.get('fiscal_type', 'service'),
                            OPERATION_TYPE[context['type']],
                            JOURNAL_TYPE[context['type']]))
                    fiscal_category_id.set('required', '1')

                document_series = eview.xpath(
                    "//field[@name='document_serie_id']")
                for document_serie_id in document_series:
                    document_serie_id.set(
                        'domain', "[('fiscal_type', '=', '%s')]"
                        % (context.get('fiscal_type', 'service')))

            if context.get('fiscal_type', False):
                delivery_infos = eview.xpath("//group[@name='delivery_info']")
                for delivery_info in delivery_infos:
                    delivery_info.set('invisible', '1')

            result['arch'] = etree.tostring(eview)

        if view_type == 'tree':
            doc = etree.XML(result['arch'])
            nodes = doc.xpath("//field[@name='partner_id']")
            partner_string = _('Customer')
            if context.get('type', 'out_invoice') in \
                    ('in_invoice', 'in_refund'):
                partner_string = _('Supplier')
            for node in nodes:
                node.set('string', partner_string)
            result['arch'] = etree.tostring(doc)
        return result

    @api.multi
    def action_number(self):
        # TODO: not correct fix but required a fresh values before reading it.
        self.write({})
        for invoice in self:
            if invoice.issuer == '0':
                sequence_obj = self.env['ir.sequence']
                sequence = sequence_obj.browse(
                    invoice.document_serie_id.internal_sequence_id.id)
                invalid_number = self.env[
                    'l10n_br_account.invoice.invalid.number'].search(
                    [('number_start', '<=', sequence.number_next),
                     ('number_end', '>=', sequence.number_next),
                     ('document_serie_id', '=', invoice.document_serie_id.id),
                     ('state', '=', 'done')])

                if invalid_number:
                    raise except_orm(
                        _(u'Número Inválido !'),
                        _("O número: %s da série: %s, esta inutilizado") % (
                            sequence.number_next,
                            invoice.document_serie_id.name))
                if invoice.fiscal_type == 'product' or invoice.type == 'out_invoice':
                    seq_number = sequence_obj.get_id(invoice.document_serie_id.internal_sequence_id.id)
                    self.write(
                        {'internal_number': seq_number, 'number': seq_number})
                else:
                    self.write(
                        {'internal_number': invoice.vendor_serie or invoice.internal_number,
                         'number': invoice.vendor_serie or invoice.internal_number})
            else:

                self.write(
                    {'internal_number': invoice.vendor_serie or invoice.internal_number,
                     'number': invoice.vendor_serie or invoice.internal_number,
                     })
            # set name in move lines
            # finalize_invoice_move_lines() can't set because internal_number is not computed
            # action_number() is called after finalize_invoice_move_lines()
            invoice_account_id = invoice.account_id.id
            index = 1
            for line in invoice.move_id.line_id:
                # line is a tuple (0, 0, {values})
                if invoice_account_id == line.account_id.id:
                   line.name = '%s/%s' % \
                                      (invoice.internal_number, index)
                index += 1
        return True

    @api.multi
    def compute_invoice_totals(self, company_currency, ref, invoice_move_lines):
        total, total_currency, invoice_move_lines = super(AccountInvoice,self).compute_invoice_totals(company_currency, ref, invoice_move_lines)
        currency = self.currency_id.with_context(date=self.date_invoice or fields.Date.context_today(self))
        total = currency.compute(self.amount_total, company_currency)
        total_currency = total
        if self.type in ('out_invoice','in_refund'):
            total_currency = total
        else:
            total_currency = total * -1
            total =  total * -1
        return total, total_currency, invoice_move_lines
    

    # TODO Talvez este metodo substitui o metodo action_move_create
    @api.multi
    def finalize_invoice_move_lines(self, move_lines):
        """ finalize_invoice_move_lines(move_lines) -> move_lines

            Hook method to be overridden in additional modules to verify and
            possibly alter the move lines to be created by an invoice, for
            special cases.
            :param move_lines: list of dictionaries with the account.move.lines
            (as for create())
            :return: the (possibly updated) final move_lines to create for this
            invoice
        """
        move_lines = super(
            AccountInvoice, self).finalize_invoice_move_lines(move_lines)
        count = 1
        result = []
        for move_line in move_lines:
            if move_line[2]['debit'] or move_line[2]['credit']:
                if move_line[2]['account_id'] == self.account_id.id:
                    move_line[2]['name'] = '%s/%s' % \
                        (self.internal_number, count)
                    count += 1
                result.append(move_line)
        # set tax_code_id False in invoice lines
        for move_line in move_lines:
            if move_line[2].get('product_id'):
                move_line[2].update({'tax_code_id': False}) 
        return result

    def _fiscal_position_map(self, result, **kwargs):
        ctx = dict(self._context)
        ctx.update({'use_domain': ('use_invoice', '=', True)})
        if ctx.get('fiscal_category_id'):
            kwargs['fiscal_category_id'] = ctx.get('fiscal_category_id')

        if not kwargs.get('fiscal_category_id'):
            return result

        company = self.env['res.company'].browse(kwargs.get('company_id'))

        fcategory = self.env['l10n_br_account.fiscal.category'].browse(
            kwargs.get('fiscal_category_id'))
        result['value']['journal_id'] = fcategory.property_journal.id
        if not result['value'].get('journal_id', False):
            raise except_orm(
                _('Nenhum Diário !'),
                _("Categoria fiscal: '%s', não tem um diário contábil para a \
                empresa %s") % (fcategory.name, company.name))
        return self.env['account.fiscal.position.rule'].with_context(
            ctx).apply_fiscal_mapping(result, **kwargs)

    @api.multi
    def onchange_fiscal_category_id(self, partner_address_id,
                                    partner_id, company_id,
                                    fiscal_category_id):
        result = {'value': {'fiscal_position': None}}
        return self._fiscal_position_map(
            result, partner_id=partner_id,
            partner_invoice_id=partner_address_id, company_id=company_id,
            fiscal_category_id=fiscal_category_id)

    @api.onchange('fiscal_document_id')
    def onchange_fiscal_document_id(self):
        if self.issuer == '0':
            self.document_serie_id = self.company_id.document_serie_service_id


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'
    
    
    
    @api.model
    #set price_total in move line instead of subtotal
    def move_line_get_item(self, line):
        result = super(AccountInvoiceLine,self).move_line_get_item(line)
        price = line.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = line.invoice_line_tax_id.compute_all_withholding(price, line.quantity, product=line.product_id, partner=line.invoice_id.partner_id)['taxes']
        withholding_amt = 0.0
        for tax in taxes :
            withholding_amt = withholding_amt + tax['amount']
        result['price'] = line.price_total - withholding_amt
        #set True product 
        # we use this to remove tax_code_id from move line
        result['product'] = True
        return result

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_id',
                 'quantity', 'product_id', 'invoice_id.partner_id',
                 'invoice_id.currency_id')
    def _compute_price(self):
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        self.price_gross = 0.0
        taxes = self.invoice_line_tax_id.compute_all(
            price, self.quantity, product=self.product_id,
            partner=self.invoice_id.partner_id,
            fiscal_position=self.fiscal_position)
        #subtract withholings to compute price subtotal
        #self.price_subtotal = taxes['total'] - taxes['total_tax_discount']
        # get line subtotal without taxes
        self.price_subtotal = taxes['total'] - (taxes['total_included'] - taxes['total']) 
        self.price_total = taxes['total']
        if self.invoice_id:
            self.price_gross = self.invoice_id.currency_id.round(
                self.price_unit * self.quantity)
            self.discount_value = self.invoice_id.currency_id.round(
                self.price_gross - taxes['total'])
            self.price_subtotal = self.invoice_id.currency_id.round(
                taxes['total'] - taxes['total_tax_discount'])
            self.price_total = self.invoice_id.currency_id.round(
                taxes['total'])

            self.price_subtotal = taxes['total'] - (taxes['total_included'] - taxes['total'])
            self.price_total = taxes['total']

    invoice_line_tax_id = fields.Many2many(
        'account.tax', 'account_invoice_line_tax', 'invoice_line_id',
        'tax_id', string='Taxes', domain=[('parent_id', '=', False)])
    fiscal_category_id = fields.Many2one(
        'l10n_br_account.fiscal.category', 'Categoria Fiscal')
    fiscal_position = fields.Many2one(
        'account.fiscal.position', u'Posição Fiscal',
        domain="[('fiscal_category_id', '=', fiscal_category_id)]")
    price_total = fields.Float(
        string='Amount', store=True, digits=dp.get_precision('Account'),
        readonly=True, compute='_compute_price')
    price_gross = fields.Float(
        string='Vlr. Bruto', store=True, compute='_compute_price',
        digits=dp.get_precision('Account'))
    total_taxes = fields.Float(
        string='Total de Tributos', requeried=True, default=0.00,
        digits=dp.get_precision('Account'))
    discount_value = fields.Float(
        string='Vlr. desconto', store=True, compute='_compute_price',
        digits=dp.get_precision('Account'))

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
                expr = "//field[@name='fiscal_category_id']"
                fiscal_categories = eview.xpath(expr)
                for fiscal_category_id in fiscal_categories:
                    fiscal_category_id.set(
                        'domain', """[('type', '=', '%s'),
                        ('journal_type', '=', '%s')]"""
                        % (OPERATION_TYPE[context['type']],
                           JOURNAL_TYPE[context['type']]))
                    fiscal_category_id.set('required', '1')

            product_ids = eview.xpath("//field[@name='product_id']")
            for product_id in product_ids:
                product_id.set('domain', "[('fiscal_type', '=', '%s')]" % (
                    context.get('fiscal_type', 'service')))

            result['arch'] = etree.tostring(eview)

        return result
