"""
ML Framework - Machine Learning Pipeline with Model Marketplace
Complete ML framework for trading strategy development.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import yfinance as yf
import joblib
import uuid
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="ML Framework",
    description="Machine Learning Pipeline for Trading Strategies",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ModelTrainingRequest(BaseModel):
    model_type: str
    symbols: List[str]
    features: List[str]
    target: str = "price_direction"
    lookback_days: int = 252
    test_size: float = 0.2
    parameters: Dict[str, Any] = {}

class PredictionRequest(BaseModel):
    model_id: str
    symbol: str
    features: Optional[Dict[str, float]] = None

class ModelInfo(BaseModel):
    model_id: str
    model_type: str
    symbols: List[str]
    features: List[str]
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    created_at: datetime
    status: str

class MLFramework:
    """Complete ML framework for trading."""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.model_types = {
            'random_forest': RandomForestClassifier,
            'gradient_boosting': GradientBoostingClassifier,
            'logistic_regression': LogisticRegression,
            'svm': SVC
        }
        self.feature_generators = {
            'sma_20': self.calculate_sma,
            'sma_50': self.calculate_sma,
            'rsi': self.calculate_rsi,
            'macd': self.calculate_macd,
            'bollinger_bands': self.calculate_bollinger_bands,
            'volume_ratio': self.calculate_volume_ratio,
            'price_momentum': self.calculate_momentum,
            'volatility': self.calculate_volatility
        }
    
    async def train_model(self, request: ModelTrainingRequest) -> ModelInfo:
        """Train a new ML model."""
        model_id = str(uuid.uuid4())
        
        try:
            # Get training data
            data = await self.prepare_training_data(request)
            
            # Split features and target
            X = data[request.features]
            y = data[request.target]
            
            # Split train/test
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=request.test_size, random_state=42
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Initialize model
            model_class = self.model_types[request.model_type]
            model = model_class(**request.parameters)
            
            # Train model
            model.fit(X_train_scaled, y_train)
            
            # Make predictions
            y_pred = model.predict(X_test_scaled)
            
            # Calculate metrics
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, average='weighted')
            recall = recall_score(y_test, y_pred, average='weighted')
            f1 = f1_score(y_test, y_pred, average='weighted')
            
            # Store model and scaler
            self.models[model_id] = model
            self.scalers[model_id] = scaler
            
            model_info = ModelInfo(
                model_id=model_id,
                model_type=request.model_type,
                symbols=request.symbols,
                features=request.features,
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1_score=f1,
                created_at=datetime.now(),
                status="trained"
            )
            
            logger.info(f"Model {model_id} trained successfully", 
                       accuracy=accuracy, precision=precision)
            
            return model_info
            
        except Exception as e:
            logger.error(f"Model training failed: {str(e)}")
            raise
    
    async def prepare_training_data(self, request: ModelTrainingRequest) -> pd.DataFrame:
        """Prepare training data with features."""
        all_data = []
        
        for symbol in request.symbols:
            # Get historical data
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=request.lookback_days)
            
            df = ticker.history(start=start_date, end=end_date)
            if df.empty:
                continue
            
            # Generate features
            for feature in request.features:
                if feature in self.feature_generators:
                    df = self.feature_generators[feature](df, feature)
            
            # Generate target (price direction)
            df['price_direction'] = (df['Close'].shift(-1) > df['Close']).astype(int)
            
            # Add symbol column
            df['symbol'] = symbol
            
            # Drop NaN values
            df = df.dropna()
            
            all_data.append(df)
        
        if not all_data:
            raise ValueError("No data available for training")
        
        # Combine all data
        combined_data = pd.concat(all_data, ignore_index=True)
        
        return combined_data
    
    def calculate_sma(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate Simple Moving Average."""
        if feature == 'sma_20':
            df['sma_20'] = df['Close'].rolling(window=20).mean()
        elif feature == 'sma_50':
            df['sma_50'] = df['Close'].rolling(window=50).mean()
        return df
    
    def calculate_rsi(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate RSI."""
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    def calculate_macd(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate MACD."""
        ema_12 = df['Close'].ewm(span=12).mean()
        ema_26 = df['Close'].ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        return df
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        df['bb_middle'] = df['Close'].rolling(window=20).mean()
        df['bb_std'] = df['Close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)
        df['bollinger_bands'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        return df
    
    def calculate_volume_ratio(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate volume ratio."""
        df['volume_sma'] = df['Volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['Volume'] / df['volume_sma']
        return df
    
    def calculate_momentum(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate price momentum."""
        df['price_momentum'] = df['Close'].pct_change(periods=10)
        return df
    
    def calculate_volatility(self, df: pd.DataFrame, feature: str) -> pd.DataFrame:
        """Calculate volatility."""
        df['returns'] = df['Close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        return df
    
    async def make_prediction(self, request: PredictionRequest) -> Dict:
        """Make prediction using trained model."""
        if request.model_id not in self.models:
            raise ValueError(f"Model {request.model_id} not found")
        
        model = self.models[request.model_id]
        scaler = self.scalers[request.model_id]
        
        try:
            # Get current features
            if request.features:
                features = list(request.features.values())
            else:
                features = await self.get_current_features(request.symbol)
            
            # Scale features
            features_scaled = scaler.transform([features])
            
            # Make prediction
            prediction = model.predict(features_scaled)[0]
            prediction_proba = model.predict_proba(features_scaled)[0]
            
            return {
                'model_id': request.model_id,
                'symbol': request.symbol,
                'prediction': int(prediction),
                'confidence': float(max(prediction_proba)),
                'probabilities': prediction_proba.tolist(),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            raise
    
    async def get_current_features(self, symbol: str) -> List[float]:
        """Get current features for a symbol."""
        # Get recent data
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")
        
        if df.empty:
            raise ValueError(f"No data available for {symbol}")
        
        # Calculate all features
        df = self.calculate_sma(df, 'sma_20')
        df = self.calculate_sma(df, 'sma_50')
        df = self.calculate_rsi(df, 'rsi')
        df = self.calculate_macd(df, 'macd')
        df = self.calculate_bollinger_bands(df, 'bollinger_bands')
        df = self.calculate_volume_ratio(df, 'volume_ratio')
        df = self.calculate_momentum(df, 'price_momentum')
        df = self.calculate_volatility(df, 'volatility')
        
        # Get latest values
        latest = df.iloc[-1]
        
        features = [
            latest.get('sma_20', 0),
            latest.get('sma_50', 0),
            latest.get('rsi', 0),
            latest.get('macd', 0),
            latest.get('bollinger_bands', 0),
            latest.get('volume_ratio', 0),
            latest.get('price_momentum', 0),
            latest.get('volatility', 0)
        ]
        
        # Replace NaN with 0
        features = [0 if pd.isna(x) else x for x in features]
        
        return features
    
    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """Get model information."""
        if model_id not in self.models:
            return None
        
        # This would typically be stored in a database
        return {
            'model_id': model_id,
            'status': 'trained',
            'created_at': datetime.now().isoformat()
        }
    
    def list_models(self) -> List[str]:
        """List all available models."""
        return list(self.models.keys())

# Initialize ML framework
ml_framework = MLFramework()

@app.get("/")
async def root():
    return {
        "service": "ml-framework",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "available_models": list(ml_framework.model_types.keys()),
        "trained_models": len(ml_framework.models)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ml-framework",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/models/train", response_model=ModelInfo)
async def train_model(request: ModelTrainingRequest):
    """Train a new ML model."""
    try:
        model_info = await ml_framework.train_model(request)
        return model_info
    except Exception as e:
        logger.error(f"Model training failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Model training failed: {str(e)}")

@app.post("/models/predict")
async def make_prediction(request: PredictionRequest):
    """Make prediction using trained model."""
    try:
        prediction = await ml_framework.make_prediction(request)
        return prediction
    except Exception as e:
        logger.error(f"Prediction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

@app.get("/models")
async def list_models():
    """List all trained models."""
    return {
        "models": ml_framework.list_models(),
        "count": len(ml_framework.models),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/models/{model_id}")
async def get_model_info(model_id: str):
    """Get model information."""
    model_info = ml_framework.get_model_info(model_id)
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    return model_info

@app.get("/features")
async def get_available_features():
    """Get list of available features."""
    return {
        "features": list(ml_framework.feature_generators.keys()),
        "count": len(ml_framework.feature_generators),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
