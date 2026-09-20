import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './state/AuthContext';
import { QuotaProvider } from './state/QuotaContext';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <QuotaProvider>
          <App />
        </QuotaProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
