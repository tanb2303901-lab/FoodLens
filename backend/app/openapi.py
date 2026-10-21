"""Describe required mutation headers without changing their domain error handling."""
from copy import deepcopy


def complete_contract(spec):
    # The owner extension has no VietFood original IDs. Describe that relation
    # for generated clients as well as enforcing it in runtime DTO validators.
    for name in ('Food','Detection'):
        then={'original_class_id':{'type':'integer','minimum':0,'maximum':67,'not':{'const':27}}}
        otherwise={'original_class_id':{'type':'null'}}
        if name=='Food':
            then['class_map_version']={'const':'vietfood-67-2026-10-12-v1'}
            otherwise['class_map_version']={'const':'foodlens-75-2026-10-16-v2'}
        spec['components']['schemas'][name]['allOf']=[{
            'if':{'properties':{'training_class_id':{'maximum':66}},'required':['training_class_id']},
            'then':{'properties':then},'else':{'properties':otherwise}}]
    required_headers = {
        'confirmScan': {'If-Match'},
    }
    for methods in spec['paths'].values():
        for method, operation in methods.items():
            if method not in {'get', 'post', 'patch', 'delete'}:
                continue
            for parameter in operation.get('parameters', []):
                if parameter.get('in') != 'header' or parameter['name'] not in required_headers.get(operation['operationId'], set()):
                    continue
                parameter['required'] = True
                parameter['schema'] = {'type': 'string', 'maxLength': 12, 'pattern': r'^"[1-9][0-9]*"$'}
                parameter['description'] = 'Quoted current ETag revision (1..2147483647). Missing: 428; stale: 412.'
            operation['responses']['500'] = {
                'description': 'Sanitized unexpected backend error.',
                'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}},
            }
            for status, response in operation['responses'].items():
                headers = response.setdefault('headers', {})
                headers['X-Request-ID'] = {'description': 'Server request identifier; matches error.request_id.',
                                           'schema': {'type': 'string', 'format': 'uuid'}}
                headers['Cache-Control'] = {'schema': {'type': 'string', 'const': 'no-store'}}
                if status == '401':
                    headers['WWW-Authenticate'] = {'schema': {'type': 'string', 'const': 'Bearer'}}
    return spec


def configure_openapi(app):
    generate = app.openapi

    def contract():
        if app.openapi_schema is None:
            app.openapi_schema = complete_contract(deepcopy(generate()))
        return app.openapi_schema

    app.openapi = contract
