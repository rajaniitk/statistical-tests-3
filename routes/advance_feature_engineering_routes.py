from flask import Blueprint, request, jsonify, session
from services.advance_feature_engineering import AdvanceFeatureEngineering
from models import Dataset, FeatureEngineering
import logging
from database import db

advance_feature_engineering_bp = Blueprint('advance_feature_engineering', __name__, url_prefix='/api/advance-feature')

@advance_feature_engineering_bp.route('/datasets', methods=['GET'])
def get_datasets():
    """Get all available datasets for analysis operations"""
    try:
        # Query all datasets from the database
        datasets = Dataset.query.all()
        dataset_list = []

        # Iterate through each dataset and format the data for JSON response
        for dataset in datasets:
            dataset_list.append({
                'id': dataset.id,
                'filename': dataset.filename,
                'rows': dataset.num_rows,
                'columns': dataset.num_columns,
                'file_size': dataset.file_size,
                # Safely format the upload timestamp:
                # If dataset.created_at is None, assign None. Otherwise, call isoformat().
                'created_at': dataset.upload_timestamp.isoformat() if dataset.upload_timestamp else None
            })

        # Return a successful JSON response with the list of datasets
        return jsonify({
            'success': True,
            'datasets': dataset_list
        })

    except Exception as e:
        # Log the error on the server side for debugging
        logging.error(f"Error fetching datasets: {str(e)}")
        # Return a JSON response indicating failure and the error message, with a 500 status code
        return jsonify({'success': False, 'error': f"An internal server error occurred while retrieving datasets: {str(e)}"}), 500

@advance_feature_engineering_bp.route('/pca/<int:dataset_id>', methods=['POST'])
def perform_pca(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        columns = request.json.get('columns')
        n_components = request.json.get('n_components', 2)
        
        result = engineer.pca_analysis(dataset_id, n_components, columns)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"PCA error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/feature-selection/<int:dataset_id>', methods=['POST'])
def feature_selection(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        target_column = request.json.get('target_column')
        method = request.json.get('method', 'selectkbest')
        k = request.json.get('k', 10)
        
        if not target_column:
            return jsonify({'success': False, 'error': 'Target column is required'}), 400
        
        result = engineer.feature_selection(dataset_id, target_column, method, k)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"Feature selection error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/dimensionality-reduction/<int:dataset_id>', methods=['POST'])
def dimensionality_reduction(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        method = request.json.get('method', 'tsne')
        n_components = request.json.get('n_components', 2)
        columns = request.json.get('columns')
        
        result = engineer.dimensionality_reduction(dataset_id, method, n_components, columns)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"Dimensionality reduction error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/clustering/<int:dataset_id>', methods=['POST'])
def clustering_analysis(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        algorithm = request.json.get('algorithm', 'kmeans')
        n_clusters = request.json.get('n_clusters', 3)
        columns = request.json.get('columns')
        
        result = engineer.clustering_analysis(dataset_id, algorithm, n_clusters, columns)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"Clustering error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/rfe/<int:dataset_id>', methods=['POST'])
def rfe_analysis(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        target_column = request.json.get('target_column')
        n_features = request.json.get('n_features', 10)
        estimator = request.json.get('estimator', 'random_forest')
        
        if not target_column:
            return jsonify({'success': False, 'error': 'Target column is required'}), 400
        
        result = engineer.rfe_analysis(dataset_id, target_column, n_features, estimator)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"RFE error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/time-features/<int:dataset_id>', methods=['POST'])
def time_features(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        column = request.json.get('column')
        features = request.json.get('features', [])
        
        if not column:
            return jsonify({'success': False, 'error': 'Column parameter is required'}), 400
        
        if not features:
            return jsonify({'success': False, 'error': 'Features parameter is required'}), 400
        
        result = engineer.time_series_features(dataset_id, column, features)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"Time features error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@advance_feature_engineering_bp.route('/text-features/<int:dataset_id>', methods=['POST'])
def text_features(dataset_id):
    try:
        engineer = AdvanceFeatureEngineering()
        
        column = request.json.get('column')
        features = request.json.get('features', [])
        
        if not column:
            return jsonify({'success': False, 'error': 'Column parameter is required'}), 400
        
        if not features:
            return jsonify({'success': False, 'error': 'Features parameter is required'}), 400
        
        result = engineer.text_features(dataset_id, column, features)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
            
    except Exception as e:
        logging.error(f"Text features error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
