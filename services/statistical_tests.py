import pandas as pd
import numpy as np
import os
from scipy import stats
from scipy.stats import chi2_contingency, fisher_exact
from statsmodels.stats.contingency_tables import mcnemar
from sklearn.preprocessing import LabelEncoder
from statsmodels.stats.anova import anova_lm
from statsmodels.formula.api import ols
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.diagnostic import lilliefors
import logging
from datetime import datetime
from models import Dataset, Analysis, db
from services.data_processor import DataProcessor
from flask import current_app
import json

class StatisticalTests:
    def __init__(self):
        self.data_processor = DataProcessor()
        
    def _validate_numeric_column(self, df, column_name):
        """Helper method to validate and convert a column to numeric"""
        if column_name not in df.columns:
            return None, f'Column "{column_name}" not found in dataset'
        
        try:
            # Try to convert to numeric
            numeric_data = pd.to_numeric(df[column_name], errors='coerce')
            valid_data = numeric_data.dropna()
            
            if len(valid_data) == 0:
                return None, f'Column "{column_name}" contains no valid numeric data'
            
            if len(valid_data) < len(df[column_name]) * 0.5:
                return None, f'Column "{column_name}" contains mostly non-numeric data ({len(valid_data)}/{len(df[column_name])} valid values)'
            
            return valid_data, None
            
        except Exception as e:
            return None, f'Cannot process column "{column_name}": {str(e)}'
    
    def _get_dataset_info(self, dataset_id):
        """Helper method to get dataset and basic info"""
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if df is None or df.empty:
                return None, None, 'Dataset is empty or could not be loaded'
            
            return dataset, df, None
            
        except Exception as e:
            return None, None, f'Error loading dataset: {str(e)}'
    
    def get_descriptive_statistics_by_id(self, dataset_id, columns=None):
        """Get descriptive statistics for specified columns using dataset ID"""
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if columns:
                # Filter to requested columns
                available_cols = [col for col in columns if col in df.columns]
                if not available_cols:
                    return {'success': False, 'error': 'None of the requested columns found'}
                df = df[available_cols]
            
            # Get basic statistics
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            categorical_cols = df.select_dtypes(include=['object']).columns
            
            results = {}
            
            if len(numeric_cols) > 0:
                numeric_stats = df[numeric_cols].describe().to_dict()
                # Convert numpy types to regular Python types for JSON serialization
                for col in numeric_stats:
                    for stat in numeric_stats[col]:
                        if pd.isna(numeric_stats[col][stat]):
                            numeric_stats[col][stat] = None
                        else:
                            numeric_stats[col][stat] = float(numeric_stats[col][stat])
                results['numeric'] = numeric_stats
                
            if len(categorical_cols) > 0:
                results['categorical'] = {}
                for col in categorical_cols:
                    results['categorical'][col] = {
                        'count': int(df[col].count()),
                        'unique': int(df[col].nunique()),
                        'top': df[col].mode().iloc[0] if not df[col].mode().empty else None,
                        'freq': int(df[col].value_counts().iloc[0]) if not df[col].value_counts().empty else 0
                    }
            
            return {'success': True, 'statistics': results}
            
        except Exception as e:
            current_app.logger.error(f"Descriptive statistics error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_descriptive_statistics(self, file_path, columns=None):
        """Get descriptive statistics for specified columns"""
        try:
            filename = os.path.basename(file_path)
            df = self.data_processor.parse_file(file_path, filename)
            if df is None:
                return {'success': False, 'error': 'Failed to load dataset'}
            
            if columns:
                # Filter to requested columns
                available_cols = [col for col in columns if col in df.columns]
                if not available_cols:
                    return {'success': False, 'error': 'None of the requested columns found'}
                df = df[available_cols]
            
            # Get basic statistics
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            categorical_cols = df.select_dtypes(include=['object']).columns
            
            results = {}
            
            if len(numeric_cols) > 0:
                results['numeric'] = df[numeric_cols].describe().to_dict()
                
            if len(categorical_cols) > 0:
                results['categorical'] = {}
                for col in categorical_cols:
                    results['categorical'][col] = {
                        'count': int(df[col].count()),
                        'unique': int(df[col].nunique()),
                        'top': df[col].mode().iloc[0] if not df[col].mode().empty else None,
                        'freq': int(df[col].value_counts().iloc[0]) if not df[col].value_counts().empty else 0
                    }
            
            return {'success': True, 'statistics': results}
            
        except Exception as e:
            current_app.logger.error(f"Descriptive statistics error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_normality(self, file_path, column, test_type='shapiro'):
        """Test normality of a column"""
        try:
            filename = os.path.basename(file_path)
            df = self.data_processor.parse_file(file_path, filename)
            if df is None:
                return {'success': False, 'error': 'Failed to load dataset'}
                
            if column not in df.columns:
                return {'success': False, 'error': f'Column {column} not found'}
            
            data = df[column].dropna()
            
            if len(data) < 3:
                return {'success': False, 'error': 'Insufficient data for normality test'}
            
            results = {'test_type': test_type, 'column': column}
            
            if test_type == 'shapiro':
                if len(data) > 5000:
                    data = data.sample(5000)  # Limit for Shapiro-Wilk
                
                statistic, p_value = stats.shapiro(data)
                results.update({
                    'test_name': 'Shapiro-Wilk test',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'sample_size': len(data),
                    'is_normal': p_value > 0.05,
                    'interpretation': 'Normal distribution' if p_value > 0.05 else 'Not normally distributed'
                })
                
            return {'success': True, 'result': results}
            
        except Exception as e:
            current_app.logger.error(f"Normality test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def correlation_test(self, file_path, column1, column2, method='pearson'):
        """Test correlation between two columns"""
        try:
            filename = os.path.basename(file_path)
            df = self.data_processor.parse_file(file_path, filename)
            if df is None:
                return {'success': False, 'error': 'Failed to load dataset'}
            
            if column1 not in df.columns or column2 not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Remove missing values
            clean_data = df[[column1, column2]].dropna()
            
            if len(clean_data) < 3:
                return {'success': False, 'error': 'Insufficient data for correlation test'}
            
            x, y = clean_data[column1], clean_data[column2]
            
            if method == 'pearson':
                correlation, p_value = stats.pearsonr(x, y)
            elif method == 'spearman':
                correlation, p_value = stats.spearmanr(x, y)
            else:
                return {'success': False, 'error': f'Unknown correlation method: {method}'}
            
            results = {
                'method': method,
                'column1': column1,
                'column2': column2,
                'correlation_coefficient': float(correlation),
                'p_value': float(p_value),
                'sample_size': len(clean_data),
                'is_significant': p_value < 0.05
            }
            
            return {'success': True, 'result': results}
            
        except Exception as e:
            current_app.logger.error(f"Correlation test error: {str(e)}")
            return {'success': False, 'error': str(e)}
        
        # Define available tests and their requirements
        self.test_catalog = {
            'parametric': {
                'one_sample_ttest': {'min_samples': 1, 'data_type': 'continuous', 'distribution': 'normal'},
                'two_sample_ttest': {'min_samples': 2, 'data_type': 'continuous', 'distribution': 'normal'},
                'paired_ttest': {'min_samples': 2, 'data_type': 'continuous', 'distribution': 'normal'},
                'one_way_anova': {'min_groups': 2, 'data_type': 'continuous', 'distribution': 'normal'},
                'two_way_anova': {'min_groups': 2, 'data_type': 'continuous', 'distribution': 'normal'},
                'pearson_correlation': {'min_samples': 3, 'data_type': 'continuous', 'distribution': 'normal'}
            },
            'non_parametric': {
                'mann_whitney_u': {'min_samples': 2, 'data_type': 'ordinal', 'distribution': 'any'},
                'wilcoxon_signed_rank': {'min_samples': 2, 'data_type': 'ordinal', 'distribution': 'any'},
                'kruskal_wallis': {'min_groups': 2, 'data_type': 'ordinal', 'distribution': 'any'},
                'friedman': {'min_groups': 2, 'data_type': 'ordinal', 'distribution': 'any'},
                'spearman_correlation': {'min_samples': 3, 'data_type': 'ordinal', 'distribution': 'any'},
                'kendall_tau': {'min_samples': 3, 'data_type': 'ordinal', 'distribution': 'any'}
            },
            'categorical': {
                'chi_square_independence': {'min_samples': 5, 'data_type': 'categorical', 'distribution': 'any'},
                'chi_square_goodness_of_fit': {'min_samples': 5, 'data_type': 'categorical', 'distribution': 'any'},
                'fisher_exact': {'min_samples': 1, 'data_type': 'categorical', 'distribution': 'any'},
                'mcnemar': {'min_samples': 2, 'data_type': 'categorical', 'distribution': 'any'}
            },
            'normality': {
                'shapiro_wilk': {'min_samples': 3, 'max_samples': 5000, 'data_type': 'continuous'},
                'kolmogorov_smirnov': {'min_samples': 5, 'data_type': 'continuous'},
                'anderson_darling': {'min_samples': 5, 'data_type': 'continuous'},
                'jarque_bera': {'min_samples': 20, 'data_type': 'continuous'},
                'lilliefors': {'min_samples': 5, 'data_type': 'continuous'}
            },
            'variance': {
                'levene': {'min_groups': 2, 'data_type': 'continuous'},
                'bartlett': {'min_groups': 2, 'data_type': 'continuous', 'distribution': 'normal'},
                'fligner_killeen': {'min_groups': 2, 'data_type': 'continuous'}
            }
        }
    
    def ttest(self, dataset_id, column, test_type='one_sample', mu=0, group_column=None, column1=None, column2=None):
        try:
            # Use helper method for better error handling
            dataset, df, error = self._get_dataset_info(dataset_id)
            if error:
                return {'success': False, 'error': error}
            
            results = {'test_type': test_type, 'column': column}
            
            if test_type == 'one_sample':
                # Validate the column
                data, error = self._validate_numeric_column(df, column)
                if error:
                    return {'success': False, 'error': error}
                
                if len(data) < 3:
                    return {'success': False, 'error': f'Insufficient data for one-sample t-test. Column "{column}" has only {len(data)} valid values. At least 3 are required.'}
                
                statistic, p_value = stats.ttest_1samp(data, mu)
                results.update({
                    'null_hypothesis': f'Mean of {column} equals {mu}',
                    'alternative_hypothesis': f'Mean of {column} does not equal {mu}',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'degrees_of_freedom': len(data) - 1,
                    'sample_mean': float(data.mean()),
                    'sample_size': len(data),
                    'interpretation': self.interpret_p_value(p_value, f'reject null hypothesis that mean equals {mu}')
                })
                
            elif test_type == 'two_sample':
                if group_column is None:
                    return {'success': False, 'error': 'Group column required for two-sample t-test'}
                
                if group_column not in df.columns:
                    return {'success': False, 'error': f'Group column "{group_column}" not found'}
                
                # Validate the data column
                data, error = self._validate_numeric_column(df, column)
                if error:
                    return {'success': False, 'error': error}
                
                # Group the data
                clean_df = df[[column, group_column]].dropna()
                groups = clean_df.groupby(group_column)[column].apply(lambda x: pd.to_numeric(x, errors='coerce').dropna())
                group_names = list(groups.index)
                
                if len(group_names) != 2:
                    return {'success': False, 'error': f'Exactly two groups required for two-sample t-test. Found {len(group_names)} groups: {group_names}'}
                
                group1, group2 = groups.iloc[0], groups.iloc[1]
                
                if len(group1) < 2 or len(group2) < 2:
                    return {'success': False, 'error': f'Each group must have at least 2 observations. Group sizes: {len(group1)}, {len(group2)}'}
                
                # Equal variance test first
                levene_stat, levene_p = stats.levene(group1, group2)
                equal_var = levene_p > 0.05
                
                statistic, p_value = stats.ttest_ind(group1, group2, equal_var=equal_var)
                
                results.update({
                    'null_hypothesis': f'Means of {group_names[0]} and {group_names[1]} are equal',
                    'alternative_hypothesis': f'Means of {group_names[0]} and {group_names[1]} are not equal',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'equal_variance_assumed': equal_var,
                    'levene_test_p_value': float(levene_p),
                    'group1_mean': float(group1.mean()),
                    'group2_mean': float(group2.mean()),
                    'group1_size': len(group1),
                    'group2_size': len(group2),
                    'interpretation': self.interpret_p_value(p_value, f'reject null hypothesis that group means are equal')
                })
                
            elif test_type == 'paired':
                # For paired t-test, we need two paired columns
                if column1 and column2 and column1 in df.columns and column2 in df.columns:
                    # Validate both columns
                    data1, error1 = self._validate_numeric_column(df, column1)
                    if error1:
                        return {'success': False, 'error': f'First column: {error1}'}
                    
                    data2, error2 = self._validate_numeric_column(df, column2)
                    if error2:
                        return {'success': False, 'error': f'Second column: {error2}'}
                    
                    clean_df = df[[column1, column2]].dropna()
                    if len(clean_df) < 3:
                        return {'success': False, 'error': f'Insufficient paired data for t-test. Only {len(clean_df)} complete pairs available. At least 3 are required.'}
                    
                    numeric_df = clean_df.apply(pd.to_numeric, errors='coerce').dropna()
                    if len(numeric_df) < 3:
                        return {'success': False, 'error': f'Insufficient numeric paired data for t-test. Only {len(numeric_df)} valid numeric pairs available.'}
                    
                    statistic, p_value = stats.ttest_rel(numeric_df[column1], numeric_df[column2])
                    
                    results.update({
                        'column1': column1,
                        'column2': column2,
                        'null_hypothesis': f'Mean difference between {column1} and {column2} is zero',
                        'alternative_hypothesis': f'Mean difference between {column1} and {column2} is not zero',
                        'test_statistic': float(statistic),
                        'p_value': float(p_value),
                        'degrees_of_freedom': len(numeric_df) - 1,
                        'mean_difference': float((numeric_df[column1] - numeric_df[column2]).mean()),
                        'sample_size': len(numeric_df),
                        'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of no difference')
                    })
                else:
                    return {'success': False, 'error': 'Both columns required for paired t-test and both must exist in the dataset'}
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='ttest',
                analysis_name=f'{test_type.replace("_", " ").title()} T-Test',
                parameters={'test_type': test_type, 'column': column, 'group_column': group_column, 'mu': mu, 'column1': column1, 'column2': column2},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"T-test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def anova(self, dataset_id, dependent_var, independent_var, test_type='one_way', independent_var2=None):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if dependent_var not in df.columns or independent_var not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            if test_type == 'two_way' and (independent_var2 is None or independent_var2 not in df.columns):
                return {'success': False, 'error': 'Second independent variable required for two-way ANOVA'}
            
            # Ensure dependent variable is numeric
            try:
                df[dependent_var] = pd.to_numeric(df[dependent_var], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert dependent variable "{dependent_var}" to numeric data'}
            
            # Remove missing values
            if test_type == 'two_way':
                clean_df = df[[dependent_var, independent_var, independent_var2]].dropna()
            else:
                clean_df = df[[dependent_var, independent_var]].dropna()
            
            if len(clean_df) < 5:
                return {'success': False, 'error': 'Insufficient data for ANOVA'}
            
            if test_type == 'one_way':
                groups = clean_df.groupby(independent_var)[dependent_var].apply(list)
                
                if len(groups) < 2:
                    return {'success': False, 'error': 'At least 2 groups required for ANOVA'}
                
                # One-way ANOVA
                statistic, p_value = stats.f_oneway(*groups)
                
                # Calculate effect size (eta-squared)
                ss_between = sum([len(group) * (np.mean(group) - clean_df[dependent_var].mean())**2 for group in groups])
                ss_total = sum([(x - clean_df[dependent_var].mean())**2 for x in clean_df[dependent_var]])
                eta_squared = ss_between / ss_total if ss_total > 0 else 0
                
                results = {
                    'test_type': 'one_way_anova',
                    'dependent_variable': dependent_var,
                    'independent_variable': independent_var,
                    'null_hypothesis': f'All group means are equal across {independent_var}',
                    'alternative_hypothesis': f'At least one group mean differs across {independent_var}',
                    'f_statistic': float(statistic),
                    'p_value': float(p_value),
                    'degrees_of_freedom_between': len(groups) - 1,
                    'degrees_of_freedom_within': len(clean_df) - len(groups),
                    'eta_squared': float(eta_squared),
                    'group_statistics': {
                        str(name): {
                            'mean': float(np.mean(group)),
                            'std': float(np.std(group)),
                            'size': len(group)
                        } for name, group in groups.items()
                    },
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis that all group means are equal')
                }
                
                # Post-hoc analysis if significant
                if p_value < 0.05:
                    try:
                        tukey_results = pairwise_tukeyhsd(
                            clean_df[dependent_var], 
                            clean_df[independent_var]
                        )
                        results['post_hoc'] = {
                            'test': 'tukey_hsd',
                            'summary': str(tukey_results),
                            'reject': tukey_results.reject.tolist(),
                            'pvalues': tukey_results.pvalues.tolist()
                        }
                    except:
                        pass
            
            elif test_type == 'two_way':
                try:
                    # Two-way ANOVA using statsmodels
                    import statsmodels.api as sm
                    from statsmodels.formula.api import ols
                    
                    # Create formula for two-way ANOVA
                    formula = f'Q("{dependent_var}") ~ C(Q("{independent_var}")) + C(Q("{independent_var2}")) + C(Q("{independent_var}")):C(Q("{independent_var2}"))'
                    
                    # Fit the model
                    model = ols(formula, data=clean_df).fit()
                    anova_table = sm.stats.anova_lm(model, typ=2)
                    
                    results = {
                        'test_type': 'two_way_anova',
                        'dependent_variable': dependent_var,
                        'independent_variable1': independent_var,
                        'independent_variable2': independent_var2,
                        'null_hypothesis': 'No main effects or interaction effects',
                        'alternative_hypothesis': 'At least one main effect or interaction effect exists',
                        'anova_table': {
                            'sources': [],
                            'f_statistics': [],
                            'p_values': [],
                            'degrees_of_freedom': []
                        }
                    }
                    
                    # Extract results from ANOVA table
                    for source in anova_table.index:
                        if source != 'Residual':
                            results['anova_table']['sources'].append(str(source))
                            results['anova_table']['f_statistics'].append(float(anova_table.loc[source, 'F']))
                            results['anova_table']['p_values'].append(float(anova_table.loc[source, 'PR(>F)']))
                            results['anova_table']['degrees_of_freedom'].append(int(anova_table.loc[source, 'df']))
                    
                    # Overall interpretation
                    significant_effects = [source for source, p_val in zip(results['anova_table']['sources'], results['anova_table']['p_values']) if p_val < 0.05]
                    
                    if significant_effects:
                        results['interpretation'] = f"Significant effects found for: {', '.join(significant_effects)}"
                    else:
                        results['interpretation'] = "No significant main effects or interaction effects found"
                    
                    results['model_summary'] = str(model.summary())
                    
                except Exception as e:
                    return {'success': False, 'error': f'Two-way ANOVA failed: {str(e)}. Make sure statsmodels is installed and data is properly formatted.'}
            
            else:
                return {'success': False, 'error': f'Test type {test_type} not implemented'}
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='anova',
                analysis_name=f'{test_type.replace("_", " ").title()} ANOVA',
                parameters={'dependent_var': dependent_var, 'independent_var': independent_var, 'independent_var2': independent_var2, 'test_type': test_type},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"ANOVA error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def chi_square(self, dataset_id, column1, column2=None, test_type='independence'):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if column1 not in df.columns:
                return {'success': False, 'error': f'Column {column1} not found'}
            
            results = {'test_type': test_type, 'column1': column1}
            
            if test_type == 'independence':
                if column2 is None or column2 not in df.columns:
                    return {'success': False, 'error': 'Second column required for independence test'}
                
                # Create contingency table
                contingency_table = pd.crosstab(df[column1], df[column2])
                
                if contingency_table.size == 0:
                    return {'success': False, 'error': 'Contingency table is empty'}
                
                # Check minimum expected frequencies
                chi2_stat, p_value, dof, expected = chi2_contingency(contingency_table)
                min_expected = expected.min()
                
                results.update({
                    'column2': column2,
                    'null_hypothesis': f'{column1} and {column2} are independent',
                    'alternative_hypothesis': f'{column1} and {column2} are not independent',
                    'chi2_statistic': float(chi2_stat),
                    'p_value': float(p_value),
                    'degrees_of_freedom': int(dof),
                    'contingency_table': contingency_table.to_dict(),
                    'expected_frequencies': expected.tolist(),
                    'min_expected_frequency': float(min_expected),
                    'assumption_met': min_expected >= 5,
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of independence')
                })
                
                # Calculate effect size (Cramér's V)
                n = contingency_table.sum().sum()
                cramers_v = np.sqrt(chi2_stat / (n * (min(contingency_table.shape) - 1)))
                results['cramers_v'] = float(cramers_v)
                
            elif test_type == 'goodness_of_fit':
                observed = df[column1].value_counts().sort_index()
                expected_equal = [len(df) / len(observed)] * len(observed)
                
                chi2_stat, p_value = stats.chisquare(observed, expected_equal)
                
                results.update({
                    'null_hypothesis': f'{column1} follows uniform distribution',
                    'alternative_hypothesis': f'{column1} does not follow uniform distribution',
                    'chi2_statistic': float(chi2_stat),
                    'p_value': float(p_value),
                    'degrees_of_freedom': len(observed) - 1,
                    'observed_frequencies': observed.to_dict(),
                    'expected_frequencies': dict(zip(observed.index, expected_equal)),
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of uniform distribution')
                })
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='chi_square',
                analysis_name=f'Chi-Square {test_type.replace("_", " ").title()} Test',
                parameters={'column1': column1, 'column2': column2, 'test_type': test_type},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Chi-square error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def correlation_test(self, dataset_id, column1, column2, method='pearson'):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if column1 not in df.columns or column2 not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Remove missing values
            clean_data = df[[column1, column2]].dropna()
            
            if len(clean_data) < 3:
                return {'success': False, 'error': 'Insufficient data for correlation test'}
            
            # Ensure columns are numeric
            try:
                x = pd.to_numeric(clean_data[column1], errors='coerce')
                y = pd.to_numeric(clean_data[column2], errors='coerce')
                
                # Remove any NaN values that resulted from conversion
                mask = ~(pd.isna(x) | pd.isna(y))
                x = x[mask]
                y = y[mask]
                
                if len(x) < 3:
                    return {'success': False, 'error': f'Insufficient numeric data for correlation test. Columns "{column1}" and "{column2}" may contain non-numeric values.'}
                    
            except Exception:
                return {'success': False, 'error': f'Cannot convert columns "{column1}" and "{column2}" to numeric data'}
            
            if method == 'pearson':
                correlation, p_value = stats.pearsonr(x, y)
                test_name = 'Pearson correlation'
                assumptions = 'Linear relationship, normal distribution'
            elif method == 'spearman':
                correlation, p_value = stats.spearmanr(x, y)
                test_name = 'Spearman rank correlation'
                assumptions = 'Monotonic relationship'
            elif method == 'kendall':
                correlation, p_value = stats.kendalltau(x, y)
                test_name = 'Kendall tau correlation'
                assumptions = 'Ordinal data'
            else:
                return {'success': False, 'error': f'Unknown correlation method: {method}'}
            
            # Calculate confidence interval for Pearson
            confidence_interval = None
            if method == 'pearson' and len(x) > 3:
                z = np.arctanh(correlation)
                se = 1 / np.sqrt(len(x) - 3)
                z_lower = z - 1.96 * se
                z_upper = z + 1.96 * se
                confidence_interval = [float(np.tanh(z_lower)), float(np.tanh(z_upper))]
            
            results = {
                'test_name': test_name,
                'method': method,
                'column1': column1,
                'column2': column2,
                'null_hypothesis': f'No {method} correlation between {column1} and {column2}',
                'alternative_hypothesis': f'Significant {method} correlation between {column1} and {column2}',
                'correlation_coefficient': float(correlation),
                'p_value': float(p_value),
                'sample_size': len(x),
                'assumptions': assumptions,
                'confidence_interval_95': confidence_interval,
                'effect_size': self.interpret_correlation_strength(abs(correlation)),
                'interpretation': self.interpret_correlation(correlation, p_value)
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='correlation_test',
                analysis_name=f'{method.title()} Correlation Test',
                parameters={'column1': column1, 'column2': column2, 'method': method},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Correlation test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def normality_test(self, dataset_id, column, test_type='shapiro'):
        try:
            # Use helper method for better error handling
            dataset, df, error = self._get_dataset_info(dataset_id)
            if error:
                return {'success': False, 'error': error}
            
            # Validate the column
            data, error = self._validate_numeric_column(df, column)
            if error:
                return {'success': False, 'error': error}
            
            if len(data) < 3:
                return {'success': False, 'error': f'Insufficient data points for normality test. Column "{column}" has only {len(data)} valid numeric values. At least 3 are required.'}
            
            results = {'test_type': test_type, 'column': column}
            
            if test_type == 'shapiro':
                if len(data) > 5000:
                    return {'success': False, 'error': 'Shapiro-Wilk test limited to 5000 samples. Please use another normality test for large datasets.'}
                
                statistic, p_value = stats.shapiro(data)
                results.update({
                    'test_name': 'Shapiro-Wilk test',
                    'null_hypothesis': f'{column} follows normal distribution',
                    'alternative_hypothesis': f'{column} does not follow normal distribution',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'sample_size': len(data),
                    'interpretation': self.interpret_normality(p_value)
                })
                
            elif test_type == 'kolmogorov_smirnov':
                if len(data) < 5:
                    return {'success': False, 'error': 'Kolmogorov-Smirnov test requires at least 5 data points'}
                    
                # Test against normal distribution with sample mean and std
                statistic, p_value = stats.kstest(
                    data, 
                    lambda x: stats.norm.cdf(x, data.mean(), data.std())
                )
                results.update({
                    'test_name': 'Kolmogorov-Smirnov test',
                    'null_hypothesis': f'{column} follows normal distribution',
                    'alternative_hypothesis': f'{column} does not follow normal distribution',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'sample_size': len(data),
                    'interpretation': self.interpret_normality(p_value)
                })
                
            elif test_type == 'anderson_darling':
                if len(data) < 5:
                    return {'success': False, 'error': 'Anderson-Darling test requires at least 5 data points'}
                    
                result = stats.anderson(data, dist='norm')
                # Use 5% significance level
                critical_value = result.critical_values[2]  # 5% level
                is_normal = result.statistic < critical_value
                
                results.update({
                    'test_name': 'Anderson-Darling test',
                    'null_hypothesis': f'{column} follows normal distribution',
                    'alternative_hypothesis': f'{column} does not follow normal distribution',
                    'test_statistic': float(result.statistic),
                    'critical_values': result.critical_values.tolist(),
                    'significance_levels': result.significance_level.tolist(),
                    'is_normal_5_percent': bool(is_normal),  # Convert numpy bool to Python bool
                    'sample_size': len(data),
                    'interpretation': 'Normal distribution' if is_normal else 'Not normally distributed'
                })
                
            elif test_type == 'jarque_bera':
                if len(data) < 20:
                    return {'success': False, 'error': 'Jarque-Bera test requires at least 20 samples'}
                
                statistic, p_value = stats.jarque_bera(data)
                results.update({
                    'test_name': 'Jarque-Bera test',
                    'null_hypothesis': f'{column} follows normal distribution',
                    'alternative_hypothesis': f'{column} does not follow normal distribution',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'sample_size': len(data),
                    'interpretation': self.interpret_normality(p_value)
                })
                
            elif test_type == 'lilliefors':
                try:
                    statistic, p_value = lilliefors(data)
                    results.update({
                        'test_name': 'Lilliefors test',
                        'null_hypothesis': f'{column} follows normal distribution',
                        'alternative_hypothesis': f'{column} does not follow normal distribution',
                        'test_statistic': float(statistic),
                        'p_value': float(p_value),
                        'sample_size': len(data),
                        'interpretation': self.interpret_normality(p_value)
                    })
                except:
                    return {'success': False, 'error': 'Lilliefors test failed - requires statsmodels'}
            
            else:
                return {'success': False, 'error': f'Unknown normality test: {test_type}. Supported tests: shapiro, kolmogorov_smirnov, anderson_darling, jarque_bera, lilliefors'}
            
            # Add descriptive statistics
            results['descriptive_stats'] = {
                'mean': float(data.mean()),
                'median': float(data.median()),
                'std': float(data.std()),
                'skewness': float(stats.skew(data)),
                'kurtosis': float(stats.kurtosis(data))
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='normality_test',
                analysis_name=f'{test_type.replace("_", " ").title()} Normality Test',
                parameters={'column': column, 'test_type': test_type},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Normality test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def variance_test(self, dataset_id, columns, test_type='levene'):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if not all(col in df.columns for col in columns):
                return {'success': False, 'error': 'Some columns not found'}
            
            if len(columns) < 2:
                return {'success': False, 'error': 'At least 2 columns required for variance test'}
            
            # Ensure all columns are numeric
            try:
                for col in columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert all columns to numeric data'}
            
            # Get data for each column
            groups = [df[col].dropna() for col in columns]
            
            # Check minimum sample sizes
            if any(len(group) < 2 for group in groups):
                return {'success': False, 'error': 'All groups must have at least 2 observations'}
            
            results = {'test_type': test_type, 'columns': columns}
            
            if test_type == 'levene':
                statistic, p_value = stats.levene(*groups)
                results.update({
                    'test_name': 'Levene test for equal variances',
                    'null_hypothesis': 'All groups have equal variances',
                    'alternative_hypothesis': 'At least one group has different variance',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'degrees_of_freedom': len(columns) - 1,
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of equal variances')
                })
                
            elif test_type == 'bartlett':
                statistic, p_value = stats.bartlett(*groups)
                results.update({
                    'test_name': 'Bartlett test for equal variances',
                    'null_hypothesis': 'All groups have equal variances',
                    'alternative_hypothesis': 'At least one group has different variance',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'degrees_of_freedom': len(columns) - 1,
                    'note': 'Assumes normal distributions',
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of equal variances')
                })
                
            elif test_type == 'fligner':
                statistic, p_value = stats.fligner(*groups)
                results.update({
                    'test_name': 'Fligner-Killeen test for equal variances',
                    'null_hypothesis': 'All groups have equal variances',
                    'alternative_hypothesis': 'At least one group has different variance',
                    'test_statistic': float(statistic),
                    'p_value': float(p_value),
                    'degrees_of_freedom': len(columns) - 1,
                    'note': 'Non-parametric test',
                    'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of equal variances')
                })
            
            else:
                return {'success': False, 'error': f'Unknown variance test: {test_type}'}
            
            # Add group statistics
            results['group_statistics'] = {
                col: {
                    'variance': float(group.var()),
                    'std': float(group.std()),
                    'mean': float(group.mean()),
                    'size': len(group)
                } for col, group in zip(columns, groups)
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='variance_test',
                analysis_name=f'{test_type.title()} Variance Test',
                parameters={'columns': columns, 'test_type': test_type},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Variance test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def mann_whitney(self, dataset_id, column, group_column):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if column not in df.columns or group_column not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Ensure data column is numeric
            try:
                df[column] = pd.to_numeric(df[column], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert column "{column}" to numeric data'}
            
            groups = df.groupby(group_column)[column].apply(lambda x: x.dropna())
            
            if len(groups) != 2:
                return {'success': False, 'error': 'Exactly two groups required for Mann-Whitney U test'}
            
            group1, group2 = groups.iloc[0], groups.iloc[1]
            group_names = list(groups.index)
            
            # Check if groups have enough data
            if len(group1) < 3 or len(group2) < 3:
                return {'success': False, 'error': 'Each group must have at least 3 observations for Mann-Whitney U test'}
            
            statistic, p_value = stats.mannwhitneyu(group1, group2, alternative='two-sided')
            
            # Calculate effect size (rank-biserial correlation)
            n1, n2 = len(group1), len(group2)
            effect_size = 1 - (2 * statistic) / (n1 * n2)
            
            results = {
                'test_name': 'Mann-Whitney U test',
                'column': column,
                'group_column': group_column,
                'group_names': group_names,
                'null_hypothesis': f'Distributions of {column} are identical between groups',
                'alternative_hypothesis': f'Distributions of {column} differ between groups',
                'u_statistic': float(statistic),
                'p_value': float(p_value),
                'effect_size': float(effect_size),
                'group1_median': float(group1.median()),
                'group2_median': float(group2.median()),
                'group1_size': n1,
                'group2_size': n2,
                'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of identical distributions')
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='mann_whitney',
                analysis_name='Mann-Whitney U Test',
                parameters={'column': column, 'group_column': group_column},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Mann-Whitney test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def kruskal_wallis(self, dataset_id, dependent_var, independent_var):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if dependent_var not in df.columns or independent_var not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Ensure dependent variable is numeric
            try:
                df[dependent_var] = pd.to_numeric(df[dependent_var], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert column "{dependent_var}" to numeric data'}
            
            clean_df = df[[dependent_var, independent_var]].dropna()
            groups = clean_df.groupby(independent_var)[dependent_var].apply(list)
            
            if len(groups) < 2:
                return {'success': False, 'error': 'At least 2 groups required for Kruskal-Wallis test'}
            
            statistic, p_value = stats.kruskal(*groups)
            
            # Calculate effect size (eta-squared)
            n = len(clean_df)
            k = len(groups)
            eta_squared = (statistic - k + 1) / (n - k) if n > k else 0
            
            results = {
                'test_name': 'Kruskal-Wallis test',
                'dependent_variable': dependent_var,
                'independent_variable': independent_var,
                'null_hypothesis': f'All groups have the same distribution of {dependent_var}',
                'alternative_hypothesis': f'At least one group has a different distribution of {dependent_var}',
                'h_statistic': float(statistic),
                'p_value': float(p_value),
                'degrees_of_freedom': len(groups) - 1,
                'eta_squared': float(eta_squared),
                'group_statistics': {
                    str(name): {
                        'median': float(np.median(group)),
                        'mean_rank': float(np.mean(stats.rankdata(np.concatenate(groups))[
                            sum(len(groups[i]) for i in range(idx)):
                            sum(len(groups[i]) for i in range(idx)) + len(group)
                        ])),
                        'size': len(group)
                    } for idx, (name, group) in enumerate(groups.items())
                },
                'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of identical distributions')
            }
            
            # Post-hoc analysis if significant
            if p_value < 0.05 and len(groups) > 2:
                post_hoc_results = []
                group_names = list(groups.index)
                
                for i in range(len(group_names)):
                    for j in range(i + 1, len(group_names)):
                        try:
                            stat, p = stats.mannwhitneyu(groups.iloc[i], groups.iloc[j])
                            post_hoc_results.append({
                                'group1': str(group_names[i]),
                                'group2': str(group_names[j]),
                                'u_statistic': float(stat),
                                'p_value': float(p),
                                'significant': p < 0.05
                            })
                        except:
                            pass
                
                results['post_hoc'] = post_hoc_results
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='kruskal_wallis',
                analysis_name='Kruskal-Wallis Test',
                parameters={'dependent_var': dependent_var, 'independent_var': independent_var},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Kruskal-Wallis test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def wilcoxon(self, dataset_id, column1, column2):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if column1 not in df.columns or column2 not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Ensure columns are numeric
            try:
                df[column1] = pd.to_numeric(df[column1], errors='coerce')
                df[column2] = pd.to_numeric(df[column2], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert columns "{column1}" and "{column2}" to numeric data'}
            
            # Remove missing values
            clean_df = df[[column1, column2]].dropna()
            
            if len(clean_df) < 6:
                return {'success': False, 'error': 'At least 6 pairs required for Wilcoxon signed-rank test'}
            
            statistic, p_value = stats.wilcoxon(clean_df[column1], clean_df[column2])
            
            # Calculate effect size
            z_score = statistic / np.sqrt(len(clean_df) * (len(clean_df) + 1) * (2 * len(clean_df) + 1) / 6)
            effect_size = z_score / np.sqrt(len(clean_df))
            
            results = {
                'test_name': 'Wilcoxon signed-rank test',
                'column1': column1,
                'column2': column2,
                'null_hypothesis': f'Median difference between {column1} and {column2} is zero',
                'alternative_hypothesis': f'Median difference between {column1} and {column2} is not zero',
                'test_statistic': float(statistic),
                'p_value': float(p_value),
                'effect_size': float(effect_size),
                'sample_size': len(clean_df),
                'median_difference': float((clean_df[column1] - clean_df[column2]).median()),
                'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of no difference')
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='wilcoxon',
                analysis_name='Wilcoxon Signed-Rank Test',
                parameters={'column1': column1, 'column2': column2},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Wilcoxon test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def friedman(self, dataset_id, columns):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if not all(col in df.columns for col in columns):
                return {'success': False, 'error': 'Some columns not found'}
            
            if len(columns) < 3:
                return {'success': False, 'error': 'At least 3 columns required for Friedman test'}
            
            # Ensure all columns are numeric
            try:
                for col in columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert all columns to numeric data'}
            
            # Remove rows with any missing values
            clean_df = df[columns].dropna()
            
            if len(clean_df) < 6:
                return {'success': False, 'error': 'At least 6 complete observations required'}
            
            # Convert to array format for Friedman test
            data_arrays = [clean_df[col].values for col in columns]
            
            statistic, p_value = stats.friedmanchisquare(*data_arrays)
            
            results = {
                'test_name': 'Friedman test',
                'columns': columns,
                'null_hypothesis': 'All treatments have identical effects',
                'alternative_hypothesis': 'At least one treatment has a different effect',
                'chi2_statistic': float(statistic),
                'p_value': float(p_value),
                'degrees_of_freedom': len(columns) - 1,
                'sample_size': len(clean_df),
                'column_statistics': {
                    col: {
                        'median': float(clean_df[col].median()),
                        'mean_rank': float(np.mean(stats.rankdata(clean_df[col])))
                    } for col in columns
                },
                'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of identical effects')
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='friedman',
                analysis_name='Friedman Test',
                parameters={'columns': columns},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Friedman test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def mcnemar(self, dataset_id, column1, column2):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if column1 not in df.columns or column2 not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Create contingency table
            contingency_table = pd.crosstab(df[column1], df[column2])
            
            if contingency_table.shape != (2, 2):
                return {'success': False, 'error': 'McNemar test requires 2x2 contingency table'}
            
            # Convert to numpy array
            table = contingency_table.values
            
            # Calculate McNemar statistic
            b, c = table[0, 1], table[1, 0]  # Off-diagonal elements
            
            if b + c < 10:
                # Use exact test for small samples
                statistic = min(b, c)
                p_value = 2 * stats.binom.cdf(statistic, b + c, 0.5)
                test_type = 'exact'
            else:
                # Use chi-square approximation
                statistic = (abs(b - c) - 1) ** 2 / (b + c)  # With continuity correction
                p_value = 1 - stats.chi2.cdf(statistic, 1)
                test_type = 'chi_square'
            
            results = {
                'test_name': 'McNemar test',
                'column1': column1,
                'column2': column2,
                'null_hypothesis': 'Marginal probabilities are equal',
                'alternative_hypothesis': 'Marginal probabilities are not equal',
                'test_statistic': float(statistic),
                'p_value': float(p_value),
                'test_type': test_type,
                'contingency_table': contingency_table.to_dict(),
                'discordant_pairs': {
                    'b': int(b),  # column1=0, column2=1
                    'c': int(c),  # column1=1, column2=0
                    'total': int(b + c)
                },
                'interpretation': self.interpret_p_value(p_value, 'reject null hypothesis of equal marginal probabilities')
            }
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='mcnemar',
                analysis_name='McNemar Test',
                parameters={'column1': column1, 'column2': column2},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"McNemar test error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def multiple_comparison(self, dataset_id, dependent_var, independent_var, method='tukey'):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            if dependent_var not in df.columns or independent_var not in df.columns:
                return {'success': False, 'error': 'Required columns not found'}
            
            # Ensure dependent variable is numeric
            try:
                df[dependent_var] = pd.to_numeric(df[dependent_var], errors='coerce')
            except:
                return {'success': False, 'error': f'Cannot convert dependent variable "{dependent_var}" to numeric data'}
            
            clean_df = df[[dependent_var, independent_var]].dropna()
            
            if len(clean_df) < 10:
                return {'success': False, 'error': 'Insufficient data for multiple comparison'}
            
            groups = clean_df.groupby(independent_var)[dependent_var].apply(list)
            
            if len(groups) < 2:
                return {'success': False, 'error': 'At least 2 groups required for multiple comparison'}
            
            results = {
                'method': method,
                'dependent_variable': dependent_var,
                'independent_variable': independent_var
            }
            
            if method == 'tukey':
                try:
                    tukey_results = pairwise_tukeyhsd(
                        clean_df[dependent_var], 
                        clean_df[independent_var]
                    )
                    
                    results.update({
                        'test_name': 'Tukey HSD test',
                        'summary': str(tukey_results),
                        'group_comparisons': [
                            {
                                'group1': str(tukey_results.groupsunique[i]),
                                'group2': str(tukey_results.groupsunique[j]),
                                'mean_diff': float(tukey_results.meandiffs[idx]),
                                'p_value': float(tukey_results.pvalues[idx]),
                                'reject': bool(tukey_results.reject[idx]),
                                'confidence_interval': [
                                    float(tukey_results.confint[idx][0]),
                                    float(tukey_results.confint[idx][1])
                                ]
                            }
                            for idx, (i, j) in enumerate(zip(*np.triu_indices(len(tukey_results.groupsunique), k=1)))
                        ]
                    })
                except Exception as e:
                    return {'success': False, 'error': f'Tukey test failed: {str(e)}'}
            
            elif method in ['bonferroni', 'holm']:
                try:
                    from scipy.stats import ttest_ind
                    from statsmodels.stats.multitest import multipletests
                    
                    group_names = list(groups.index)
                    group_data = [list(groups[name]) for name in group_names]
                    
                    # Perform pairwise t-tests
                    pairwise_results = []
                    p_values = []
                    
                    for i in range(len(group_names)):
                        for j in range(i + 1, len(group_names)):
                            stat, p_val = ttest_ind(group_data[i], group_data[j])
                            pairwise_results.append({
                                'group1': str(group_names[i]),
                                'group2': str(group_names[j]),
                                'mean_diff': float(np.mean(group_data[i]) - np.mean(group_data[j])),
                                'p_value_raw': float(p_val),
                                't_statistic': float(stat)
                            })
                            p_values.append(p_val)
                    
                    # Apply multiple comparisons correction
                    if method == 'bonferroni':
                        reject, p_corrected, alpha_sidak, alpha_bonf = multipletests(p_values, method='bonferroni')
                        correction_name = 'Bonferroni'
                    else:  # holm
                        reject, p_corrected, alpha_sidak, alpha_bonf = multipletests(p_values, method='holm')
                        correction_name = 'Holm-Bonferroni'
                    
                    # Update results with corrected p-values
                    for i, result in enumerate(pairwise_results):
                        result.update({
                            'p_value': float(p_corrected[i]),
                            'reject': bool(reject[i]),
                            'significant': bool(reject[i])
                        })
                    
                    results.update({
                        'test_name': f'{correction_name} Multiple Comparisons',
                        'correction_method': method,
                        'alpha_corrected': float(alpha_bonf),
                        'group_comparisons': pairwise_results,
                        'summary': f'Performed {len(pairwise_results)} pairwise comparisons with {correction_name} correction'
                    })
                    
                except Exception as e:
                    return {'success': False, 'error': f'{method.title()} test failed: {str(e)}'}
            
            else:
                return {'success': False, 'error': f'Method {method} not implemented. Supported methods: tukey, bonferroni, holm'}
            
            # Save analysis
            analysis = Analysis(
                dataset_id=dataset_id,
                analysis_type='multiple_comparison',
                analysis_name=f'{method.title()} Multiple Comparison Test',
                parameters={'dependent_var': dependent_var, 'independent_var': independent_var, 'method': method},
                results=results
            )
            db.session.add(analysis)
            db.session.commit()
            
            return {'success': True, 'results': results}
            
        except Exception as e:
            current_app.logger.error(f"Multiple comparison error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_available_tests(self, dataset_id):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
            
            available_tests = {
                'parametric': {},
                'non_parametric': {},
                'categorical': {},
                'normality': {},
                'variance': {}
            }
            
            # Check requirements for each test
            for category, tests in self.test_catalog.items():
                for test_name, requirements in tests.items():
                    is_available = True
                    notes = []
                    
                    # Check data type requirements
                    if requirements.get('data_type') == 'continuous' and len(numeric_cols) == 0:
                        is_available = False
                        notes.append('No continuous variables available')
                    elif requirements.get('data_type') == 'categorical' and len(categorical_cols) == 0:
                        is_available = False
                        notes.append('No categorical variables available')
                    
                    # Check sample size requirements
                    if 'min_samples' in requirements:
                        min_samples = requirements['min_samples']
                        if len(df) < min_samples:
                            is_available = False
                            notes.append(f'Minimum {min_samples} samples required')
                    
                    if 'max_samples' in requirements:
                        max_samples = requirements['max_samples']
                        if len(df) > max_samples:
                            is_available = False
                            notes.append(f'Maximum {max_samples} samples allowed')
                    
                    # Check group requirements
                    if 'min_groups' in requirements:
                        min_groups = requirements['min_groups']
                        if len(categorical_cols) == 0:
                            is_available = False
                            notes.append(f'No grouping variables available')
                        else:
                            max_groups = max([df[col].nunique() for col in categorical_cols])
                            if max_groups < min_groups:
                                is_available = False
                                notes.append(f'Minimum {min_groups} groups required')
                    
                    available_tests[category][test_name] = {
                        'available': is_available,
                        'requirements': requirements,
                        'notes': notes
                    }
            
            # Add dataset-specific recommendations
            recommendations = []
            
            if len(numeric_cols) >= 2:
                recommendations.append({
                    'test': 'pearson_correlation',
                    'reason': 'Multiple numeric variables available for correlation analysis'
                })
            
            if len(categorical_cols) >= 1 and len(numeric_cols) >= 1:
                recommendations.append({
                    'test': 'one_way_anova',
                    'reason': 'Categorical and numeric variables available for group comparison'
                })
            
            if len(categorical_cols) >= 2:
                recommendations.append({
                    'test': 'chi_square_independence',
                    'reason': 'Multiple categorical variables available for independence testing'
                })
            
            for col in numeric_cols:
                if len(df[col].dropna()) >= 8:
                    recommendations.append({
                        'test': 'shapiro_wilk',
                        'reason': f'Check normality of {col}'
                    })
                    break
            
            return {
                'success': True,
                'available_tests': available_tests,
                'recommendations': recommendations,
                'dataset_summary': {
                    'total_rows': len(df),
                    'numeric_columns': len(numeric_cols),
                    'categorical_columns': len(categorical_cols),
                    'numeric_cols': numeric_cols,
                    'categorical_cols': categorical_cols
                }
            }
            
        except Exception as e:
            current_app.logger.error(f"Get available tests error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_test_recommendations(self, dataset_id, context=None):
        try:
            dataset = Dataset.query.get_or_404(dataset_id)
            df = self.data_processor.load_dataset(dataset)
            
            recommendations = []
            
            # Get column types
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
            
            # Correlation analysis recommendations
            if len(numeric_cols) >= 2:
                recommendations.append({
                    'category': 'correlation',
                    'test': 'pearson_correlation',
                    'priority': 'high',
                    'reason': 'Multiple numeric variables detected',
                    'suggestion': 'Analyze relationships between numeric variables',
                    'columns': numeric_cols[:5]  # Limit to first 5
                })
            
            # Group comparison recommendations
            for cat_col in categorical_cols:
                unique_groups = df[cat_col].nunique()
                if 2 <= unique_groups <= 10:  # Reasonable number of groups
                    for num_col in numeric_cols[:3]:  # Limit to first 3 numeric
                        if unique_groups == 2:
                            recommendations.append({
                                'category': 'group_comparison',
                                'test': 'two_sample_ttest',
                                'priority': 'medium',
                                'reason': f'Two groups in {cat_col}',
                                'suggestion': f'Compare {num_col} between groups',
                                'dependent_var': num_col,
                                'grouping_var': cat_col
                            })
                        else:
                            recommendations.append({
                                'category': 'group_comparison',
                                'test': 'one_way_anova',
                                'priority': 'medium',
                                'reason': f'{unique_groups} groups in {cat_col}',
                                'suggestion': f'Compare {num_col} across groups',
                                'dependent_var': num_col,
                                'grouping_var': cat_col
                            })
            
            # Independence testing for categorical variables
            if len(categorical_cols) >= 2:
                for i, col1 in enumerate(categorical_cols[:3]):
                    for col2 in categorical_cols[i+1:4]:
                        recommendations.append({
                            'category': 'independence',
                            'test': 'chi_square_independence',
                            'priority': 'medium',
                            'reason': 'Multiple categorical variables',
                            'suggestion': f'Test independence between {col1} and {col2}',
                            'column1': col1,
                            'column2': col2
                        })
            
            # Normality testing recommendations
            for col in numeric_cols[:5]:  # Limit to first 5
                sample_size = len(df[col].dropna())
                if sample_size >= 8:
                    if sample_size <= 5000:
                        test = 'shapiro_wilk'
                        reason = 'Gold standard for normality testing'
                    else:
                        test = 'kolmogorov_smirnov'
                        reason = 'Suitable for large samples'
                    
                    recommendations.append({
                        'category': 'normality',
                        'test': test,
                        'priority': 'low',
                        'reason': reason,
                        'suggestion': f'Check if {col} follows normal distribution',
                        'column': col
                    })
            
            # Variance homogeneity testing
            if len(numeric_cols) >= 2:
                recommendations.append({
                    'category': 'variance',
                    'test': 'levene',
                    'priority': 'low',
                    'reason': 'Check equal variance assumption',
                    'suggestion': 'Test homogeneity of variances',
                    'columns': numeric_cols[:4]  # Limit to first 4
                })
            
            # Sort by priority
            priority_order = {'high': 3, 'medium': 2, 'low': 1}
            recommendations.sort(key=lambda x: priority_order.get(x['priority'], 0), reverse=True)
            
            return {
                'success': True,
                'recommendations': recommendations[:10],  # Limit to top 10
                'summary': {
                    'total_recommendations': len(recommendations),
                    'high_priority': len([r for r in recommendations if r['priority'] == 'high']),
                    'medium_priority': len([r for r in recommendations if r['priority'] == 'medium']),
                    'low_priority': len([r for r in recommendations if r['priority'] == 'low'])
                }
            }
            
        except Exception as e:
            current_app.logger.error(f"Test recommendations error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    # Helper methods for interpretation
    def interpret_p_value(self, p_value, rejection_statement, alpha=0.05):
        if p_value < alpha:
            significance = 'significant'
            conclusion = f'Result is statistically significant (p < {alpha}). {rejection_statement}.'
        else:
            significance = 'not_significant'
            conclusion = f'Result is not statistically significant (p ≥ {alpha}). Fail to reject null hypothesis.'
        
        return {
            'significance': significance,
            'conclusion': conclusion,
            'p_value': float(p_value),
            'alpha': alpha
        }
    
    def interpret_correlation(self, correlation, p_value, alpha=0.05):
        strength = self.interpret_correlation_strength(abs(correlation))
        direction = 'positive' if correlation > 0 else 'negative' if correlation < 0 else 'none'
        significance = 'significant' if p_value < alpha else 'not significant'
        
        interpretation = f"{strength['description']} {direction} correlation"
        if significance == 'significant':
            interpretation += f" (statistically significant, p = {p_value:.4f})"
        else:
            interpretation += f" (not statistically significant, p = {p_value:.4f})"
        
        return {
            'strength': strength,
            'direction': direction,
            'significance': significance,
            'interpretation': interpretation
        }
    
    def interpret_correlation_strength(self, abs_correlation):
        if abs_correlation < 0.1:
            return {'level': 'negligible', 'description': 'Negligible'}
        elif abs_correlation < 0.3:
            return {'level': 'weak', 'description': 'Weak'}
        elif abs_correlation < 0.5:
            return {'level': 'moderate', 'description': 'Moderate'}
        elif abs_correlation < 0.7:
            return {'level': 'strong', 'description': 'Strong'}
        else:
            return {'level': 'very_strong', 'description': 'Very strong'}
    
    def interpret_normality(self, p_value, alpha=0.05):
        if p_value > alpha:
            return {
                'is_normal': True,
                'conclusion': f'Data appears to be normally distributed (p = {p_value:.4f} > {alpha})'
            }
        else:
            return {
                'is_normal': False,
                'conclusion': f'Data does not appear to be normally distributed (p = {p_value:.4f} ≤ {alpha})'
            }
